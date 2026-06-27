package cli

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"

	"github.com/spf13/cobra"

	"github.com/spykeautomation/spyke/spykecore/workspace"
)

func newCreateCmd() *cobra.Command {
	var description string
	cmd := &cobra.Command{
		Use:   "create <name> [dir]",
		Short: "Create a new project and scaffold a local workspace",
		Args:  cobra.RangeArgs(1, 2),
		RunE: func(cmd *cobra.Command, args []string) error {
			e := newEnv()
			if err := e.requireAuth(); err != nil {
				return err
			}
			name := args[0]
			dir := "."
			if len(args) == 2 {
				dir = args[1]
			}
			root, err := filepath.Abs(dir)
			if err != nil {
				return err
			}
			if err := ensureNoWorkspace(root); err != nil {
				return err
			}

			proj, err := e.client.CreateProject(e.ctx, name, description)
			if err != nil {
				return err
			}
			cfg := workspace.Config{
				ServerURL:     e.server,
				ProjectID:     proj.ID,
				ProjectSlug:   proj.Slug,
				DefaultBranch: "main",
			}
			if _, err := workspace.Create(root, cfg, workspace.Head{Branch: "main"}, workspace.Index{}); err != nil {
				return err
			}
			if e.p.JSON {
				return e.p.EmitJSON(map[string]any{"project": proj, "dir": root})
			}
			e.p.Logf("Created project #%d %q (empty main branch) in %s\n", proj.ID, proj.Name, root)
			e.p.Logf("Drop in your L5X files, then `spyke commit` and `spyke push`.\n")
			return nil
		},
	}
	cmd.Flags().StringVarP(&description, "description", "d", "", "project description")
	return cmd
}

func newCloneCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "clone <project-id> [dir]",
		Short: "Download a project into a new workspace",
		Args:  cobra.RangeArgs(1, 2),
		RunE: func(cmd *cobra.Command, args []string) error {
			e := newEnv()
			if err := e.requireAuth(); err != nil {
				return err
			}
			pid, err := strconv.Atoi(args[0])
			if err != nil {
				return usageErr("project id must be a number: %q", args[0])
			}
			proj, err := e.client.GetProject(e.ctx, pid)
			if err != nil {
				return err
			}
			dir := args[0]
			if proj.Slug != "" {
				dir = proj.Slug
			}
			if len(args) == 2 {
				dir = args[1]
			}
			root, err := filepath.Abs(dir)
			if err != nil {
				return err
			}
			if err := ensureNoWorkspace(root); err != nil {
				return err
			}

			branch := "main"
			head := ""
			if commits, _, err := e.client.Log(e.ctx, pid, branch, 1, 0); err == nil && len(commits) > 0 {
				head = commits[0].SHA
			}

			files, err := e.client.ListFiles(e.ctx, pid, branch)
			if err != nil {
				return err
			}
			index := workspace.Index{}
			for _, f := range files {
				local, ok := workspace.LocalPathFor(f.Path)
				if !ok {
					e.p.Logf("skipping unrecognized path %q\n", f.Path)
					continue
				}
				data, err := e.client.DownloadFile(e.ctx, pid, branch, workspace.RepoSourcePath(f.Path))
				if err != nil {
					return fmt.Errorf("downloading %s: %w", f.Path, err)
				}
				dest := filepath.Join(root, local)
				if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil {
					return err
				}
				if err := os.WriteFile(dest, data, 0o644); err != nil {
					return err
				}
				index[f.Path] = workspace.IndexEntry{
					SHA256:    workspace.HashBytes(data),
					Size:      int64(len(data)),
					SyncedSHA: head,
				}
			}

			cfg := workspace.Config{
				ServerURL:     e.server,
				ProjectID:     proj.ID,
				ProjectSlug:   proj.Slug,
				DefaultBranch: branch,
			}
			if _, err := workspace.Create(root, cfg, workspace.Head{Branch: branch, CommitSHA: head}, index); err != nil {
				return err
			}
			if e.p.JSON {
				return e.p.EmitJSON(map[string]any{"project": proj, "dir": root, "branch": branch, "files": len(index)})
			}
			e.p.Logf("Cloned #%d %q into %s (%d file(s) on %s)\n", proj.ID, proj.Name, root, len(index), branch)
			return nil
		},
	}
	return cmd
}

// ensureNoWorkspace fails if root already contains a .spyke directory.
func ensureNoWorkspace(root string) error {
	if info, err := os.Stat(filepath.Join(root, workspace.Dir)); err == nil && info.IsDir() {
		return usageErr("%s already contains a %s workspace", root, workspace.Dir)
	}
	return nil
}
