package cli

import (
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/spf13/cobra"

	"github.com/spykeautomation/spyke/spykecore/client"
	"github.com/spykeautomation/spyke/spykecore/workspace"
)

func newStatusCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "status",
		Short: "Show the working tree status (works offline)",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, args []string) error {
			e := newEnv()
			w, err := workspace.Find("")
			if err != nil {
				return err
			}
			idx, err := w.LoadIndex()
			if err != nil {
				return err
			}
			working, err := workspace.Scan(w.Root)
			if err != nil {
				return err
			}
			changes := workspace.Diff(idx, working)
			pending, err := w.ListPending()
			if err != nil {
				return err
			}

			if e.p.JSON {
				return e.p.EmitJSON(map[string]any{
					"branch":          w.Head.Branch,
					"synced_commit":   w.Head.CommitSHA,
					"pending_commits": len(pending),
					"changes":         changes,
				})
			}

			e.p.Printf("On branch %s\n", w.Head.Branch)
			if len(pending) > 0 {
				e.p.Printf("\n%d local commit(s) to push:\n", len(pending))
				for _, pc := range pending {
					e.p.Printf("  (%d) %s  [%d file(s)]\n", pc.Seq, pc.Title, len(pc.Files))
				}
			}
			if len(changes) == 0 {
				if len(pending) == 0 {
					e.p.Printf("\nnothing to commit, working tree clean\n")
				}
				return nil
			}
			e.p.Printf("\nChanges not yet committed:\n")
			hasDeleted := false
			for _, c := range changes {
				if c.Status == "deleted" {
					hasDeleted = true
				}
				e.p.Printf("  %-10s %s\n", c.Status+":", c.Logical)
			}
			if hasDeleted {
				e.p.Logf("\nnote: deletions can't be pushed (the API has no delete) and are skipped by commit/push\n")
			}
			return nil
		},
	}
}

func newCommitCmd() *cobra.Command {
	var title, description string
	cmd := &cobra.Command{
		Use:   "commit [paths...]",
		Short: "Queue a commit of changed files locally (run push to upload)",
		Long: "Snapshot changed files into a local pending commit. A commit exists on the\n" +
			"server only after `spyke push`. With no paths, all added/modified files are\n" +
			"included; deletions are never included (the API has no delete).",
		RunE: func(cmd *cobra.Command, args []string) error {
			e := newEnv()
			if strings.TrimSpace(title) == "" {
				return usageErr("a commit message is required (-m)")
			}
			w, err := workspace.Find("")
			if err != nil {
				return err
			}
			idx, err := w.LoadIndex()
			if err != nil {
				return err
			}
			working, err := workspace.Scan(w.Root)
			if err != nil {
				return err
			}
			changes := workspace.Diff(idx, working)

			selectable := map[string]bool{}
			deleted := 0
			for _, c := range changes {
				switch c.Status {
				case "added", "modified":
					selectable[c.Logical] = true
				case "deleted":
					deleted++
				}
			}

			var chosen []string
			if len(args) > 0 {
				for _, a := range args {
					logical := resolveArgToLogical(w.Root, a)
					if !selectable[logical] {
						return usageErr("%q has no committable changes", a)
					}
					chosen = append(chosen, logical)
				}
			} else {
				for l := range selectable {
					chosen = append(chosen, l)
				}
			}
			if len(chosen) == 0 {
				return usageErr("nothing to commit")
			}
			sort.Strings(chosen)

			files := map[string][]byte{}
			for _, logical := range chosen {
				if err := workspace.ValidateLogical(logical); err != nil {
					return err
				}
				data, err := os.ReadFile(filepath.Join(w.Root, working[logical].Local))
				if err != nil {
					return err
				}
				files[logical] = data
			}

			seq, err := w.QueueCommit(title, description, files)
			if err != nil {
				return err
			}
			// Advance the baseline so the next status/commit diffs against this commit.
			for logical, data := range files {
				prev := idx[logical]
				idx[logical] = workspace.IndexEntry{
					SHA256:    workspace.HashBytes(data),
					Size:      int64(len(data)),
					SyncedSHA: prev.SyncedSHA,
				}
			}
			if err := w.SaveIndex(idx); err != nil {
				return err
			}

			if e.p.JSON {
				return e.p.EmitJSON(map[string]any{
					"queued_commit":     seq,
					"files":             chosen,
					"skipped_deletions": deleted,
				})
			}
			e.p.Logf("Queued commit (%d) %q with %d file(s). Run `spyke push` to upload.\n", seq, title, len(chosen))
			if deleted > 0 {
				e.p.Logf("note: %d deleted file(s) were not included (the API has no delete).\n", deleted)
			}
			return nil
		},
	}
	cmd.Flags().StringVarP(&title, "message", "m", "", "commit title (required)")
	cmd.Flags().StringVarP(&description, "description", "d", "", "commit description")
	return cmd
}

func newPushCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "push",
		Short: "Upload queued commits to the server",
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
			pending, err := w.ListPending()
			if err != nil {
				return err
			}
			if len(pending) == 0 {
				if e.p.JSON {
					return e.p.EmitJSON(map[string]any{"pushed": []any{}})
				}
				e.p.Logf("nothing to push\n")
				return nil
			}
			idx, err := w.LoadIndex()
			if err != nil {
				return err
			}

			pushed := []map[string]any{}
			for _, pc := range pending {
				var parts []client.FilePart
				var open []*os.File
				for _, f := range pc.Files {
					fh, err := os.Open(pc.BlobPath(f))
					if err != nil {
						closeAll(open)
						return err
					}
					open = append(open, fh)
					parts = append(parts, client.FilePart{Name: "files", Filename: f.Upload, Content: fh})
				}
				res, err := e.client.Upload(e.ctx, w.Config.ProjectID, w.Head.Branch, pc.Title, pc.Description, parts)
				closeAll(open)
				if err != nil {
					if len(pushed) > 0 {
						e.p.Logf("pushed %d commit(s) before the failure; the rest stay queued\n", len(pushed))
					}
					return err
				}
				w.Head.CommitSHA = res.SHA
				for _, f := range pc.Files {
					ent := idx[f.Logical]
					ent.SyncedSHA = res.SHA
					idx[f.Logical] = ent
				}
				_ = w.SaveHead()
				_ = w.SaveIndex(idx)
				if err := w.RemovePending(pc.Seq); err != nil {
					return err
				}
				pushed = append(pushed, map[string]any{"seq": pc.Seq, "sha": res.SHA, "title": pc.Title})
				e.p.Logf("pushed (%d) %s -> %s\n", pc.Seq, pc.Title, short(res.SHA))
			}
			if e.p.JSON {
				return e.p.EmitJSON(map[string]any{"pushed": pushed})
			}
			return nil
		},
	}
}

// resolveArgToLogical maps a commit pathspec (a logical path, or a working-tree
// path) to its logical path.
func resolveArgToLogical(root, arg string) string {
	if strings.HasPrefix(arg, "l5x/") || strings.HasPrefix(arg, "files/") {
		return arg
	}
	rel := arg
	if filepath.IsAbs(arg) {
		if r, err := filepath.Rel(root, arg); err == nil {
			rel = r
		}
	}
	return workspace.LogicalForLocal(rel)
}

func closeAll(fs []*os.File) {
	for _, f := range fs {
		_ = f.Close()
	}
}
