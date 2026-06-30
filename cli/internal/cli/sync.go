package cli

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/spf13/cobra"

	"github.com/spykeautomation/spyke/spykecore/client"
	"github.com/spykeautomation/spyke/spykecore/workspace"
)

func newPullCmd() *cobra.Command {
	var force bool
	cmd := &cobra.Command{
		Use:   "pull",
		Short: "Download new commits on the current branch (fast-forward)",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, args []string) error {
			e := newEnv()
			if err := e.requireAuth(); err != nil {
				return err
			}
			w, err := workspace.Find("")
			if err != nil {
				return err
			}
			pid := w.Config.ProjectID
			branch := w.Head.Branch

			commits, _, err := e.client.Log(e.ctx, pid, branch, 1, 0)
			if err != nil {
				return err
			}
			tip := ""
			if len(commits) > 0 {
				tip = commits[0].SHA
			}
			if tip == "" {
				e.p.Logf("branch %s has no commits on the server yet\n", branch)
				return nil
			}
			if tip == w.Head.CommitSHA {
				if e.p.JSON {
					return e.p.EmitJSON(map[string]any{"updated": false, "branch": branch, "commit": tip})
				}
				e.p.Logf("Already up to date (%s)\n", short(tip))
				return nil
			}

			idx, err := w.LoadIndex()
			if err != nil {
				return err
			}
			working, err := workspace.Scan(w.Root)
			if err != nil {
				return err
			}
			localChanged := map[string]bool{}
			for _, c := range workspace.Diff(idx, working) {
				localChanged[c.Logical] = true
			}
			pending, err := w.ListPending()
			if err != nil {
				return err
			}
			for _, pc := range pending {
				for _, f := range pc.Files {
					localChanged[f.Logical] = true
				}
			}

			// What changed on the server since our last sync.
			var remote []client.ChangedFile
			if w.Head.CommitSHA != "" {
				m, err := e.client.DiffManifest(e.ctx, pid, w.Head.CommitSHA, tip)
				if err != nil {
					return err
				}
				remote = m.Files
			} else {
				files, err := e.client.ListFiles(e.ctx, pid, tip)
				if err != nil {
					return err
				}
				for _, f := range files {
					remote = append(remote, client.ChangedFile{Path: f.Path, Kind: f.Kind, Change: "added"})
				}
			}

			var conflicts []string
			for _, rf := range remote {
				if localChanged[rf.Path] {
					conflicts = append(conflicts, rf.Path)
				}
			}
			if len(conflicts) > 0 && !force {
				sort.Strings(conflicts)
				return conflictErr("local changes would be overwritten by pull: %s (commit/push them, or use --force)", strings.Join(conflicts, ", "))
			}

			applied := 0
			for _, rf := range remote {
				local, ok := workspace.LocalPathFor(rf.Path)
				if !ok {
					continue
				}
				dest := filepath.Join(w.Root, local)
				if rf.Change == "removed" {
					_ = os.Remove(dest)
					delete(idx, rf.Path)
					applied++
					continue
				}
				data, err := e.client.DownloadFile(e.ctx, pid, tip, workspace.RepoSourcePath(rf.Path))
				if err != nil {
					return err
				}
				if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil {
					return err
				}
				if err := os.WriteFile(dest, data, 0o644); err != nil {
					return err
				}
				idx[rf.Path] = workspace.IndexEntry{SHA256: workspace.HashBytes(data), Size: int64(len(data)), SyncedSHA: tip}
				applied++
			}

			w.Head.CommitSHA = tip
			if err := w.SaveHead(); err != nil {
				return err
			}
			if err := w.SaveIndex(idx); err != nil {
				return err
			}
			if e.p.JSON {
				return e.p.EmitJSON(map[string]any{"updated": true, "branch": branch, "commit": tip, "files": applied})
			}
			e.p.Logf("Updated %s to %s (%d file(s))\n", branch, short(tip), applied)
			return nil
		},
	}
	cmd.Flags().BoolVar(&force, "force", false, "overwrite local changes with the server version")
	return cmd
}

func newCheckoutCmd() *cobra.Command {
	var create bool
	var from string
	var force bool
	cmd := &cobra.Command{
		Use:   "checkout <branch>",
		Short: "Switch branches and refresh the working tree",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			e := newEnv()
			if err := e.requireAuth(); err != nil {
				return err
			}
			w, err := workspace.Find("")
			if err != nil {
				return err
			}
			pid := w.Config.ProjectID
			target := args[0]

			idx, err := w.LoadIndex()
			if err != nil {
				return err
			}
			working, err := workspace.Scan(w.Root)
			if err != nil {
				return err
			}
			if !force {
				if ch := workspace.Diff(idx, working); len(ch) > 0 {
					return conflictErr("you have uncommitted changes — commit, push, or use --force")
				}
				if pending, _ := w.ListPending(); len(pending) > 0 {
					return conflictErr("you have unpushed commits — push them or use --force")
				}
			}

			branches, err := e.client.ListBranches(e.ctx, pid)
			if err != nil {
				return err
			}
			exists := false
			for _, b := range branches {
				if b.Name == target {
					exists = true
					break
				}
			}
			if !exists {
				if !create {
					return usageErr("branch %q does not exist (use -b to create it)", target)
				}
				start := from
				if start == "" {
					start = w.Head.Branch
				}
				if _, err := e.client.CreateBranch(e.ctx, pid, target, start); err != nil {
					return err
				}
			}

			commits, _, _ := e.client.Log(e.ctx, pid, target, 1, 0)
			tip := ""
			if len(commits) > 0 {
				tip = commits[0].SHA
			}
			files, err := e.client.ListFiles(e.ctx, pid, target)
			if err != nil {
				return err
			}
			want := map[string]bool{}
			for _, f := range files {
				want[f.Path] = true
			}
			// Remove tracked files that aren't present on the target branch.
			for logical := range idx {
				if !want[logical] {
					if local, ok := workspace.LocalPathFor(logical); ok {
						_ = os.Remove(filepath.Join(w.Root, local))
					}
				}
			}
			newIdx := workspace.Index{}
			for _, f := range files {
				local, ok := workspace.LocalPathFor(f.Path)
				if !ok {
					continue
				}
				data, err := e.client.DownloadFile(e.ctx, pid, target, workspace.RepoSourcePath(f.Path))
				if err != nil {
					return err
				}
				dest := filepath.Join(w.Root, local)
				if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil {
					return err
				}
				if err := os.WriteFile(dest, data, 0o644); err != nil {
					return err
				}
				newIdx[f.Path] = workspace.IndexEntry{SHA256: workspace.HashBytes(data), Size: int64(len(data)), SyncedSHA: tip}
			}

			w.Head = workspace.Head{Branch: target, CommitSHA: tip}
			if err := w.SaveHead(); err != nil {
				return err
			}
			if err := w.SaveIndex(newIdx); err != nil {
				return err
			}
			if e.p.JSON {
				return e.p.EmitJSON(map[string]any{"branch": target, "commit": tip, "files": len(newIdx)})
			}
			e.p.Logf("Switched to branch %s (%d file(s))\n", target, len(newIdx))
			return nil
		},
	}
	cmd.Flags().BoolVarP(&create, "create", "b", false, "create the branch if it doesn't exist")
	cmd.Flags().StringVar(&from, "from", "", "start point when creating (default: current branch)")
	cmd.Flags().BoolVar(&force, "force", false, "discard uncommitted changes / unpushed commits")
	return cmd
}

// conflictErr builds a 409-style error (exit code 4).
func conflictErr(format string, a ...any) error {
	return &client.APIError{Status: 409, Code: client.CodeConflict, Message: fmt.Sprintf(format, a...)}
}
