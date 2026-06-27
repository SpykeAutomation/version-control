package cli

import (
	"fmt"
	"os"
	"strings"

	"github.com/spf13/cobra"

	"github.com/spykeautomation/spyke/spykecore/client"
	"github.com/spykeautomation/spyke/spykecore/workspace"
)

func newFilesCmd() *cobra.Command {
	var ref string
	cmd := &cobra.Command{
		Use:   "files",
		Short: "List the project's files at a ref",
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
			if ref == "" {
				ref = w.Head.Branch
			}
			files, err := e.client.ListFiles(e.ctx, w.Config.ProjectID, ref)
			if err != nil {
				return err
			}
			if e.p.JSON {
				return e.p.EmitJSON(files)
			}
			for _, f := range files {
				e.p.Printf("%-5s %10d  %s\n", f.Kind, f.Size, f.Path)
			}
			return nil
		},
	}
	cmd.Flags().StringVar(&ref, "ref", "", "ref to list (default: current branch)")
	return cmd
}

func newCatCmd() *cobra.Command {
	var ref string
	cmd := &cobra.Command{
		Use:   "cat <repo-path>",
		Short: "Write a tracked file's bytes at a ref to stdout",
		Long:  "repo-path is a path from `spyke files`, e.g. l5x/Line1/source.L5X or files/docs/io.csv.",
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
			if ref == "" {
				ref = w.Head.Branch
			}
			data, err := e.client.DownloadFile(e.ctx, w.Config.ProjectID, ref, args[0])
			if err != nil {
				return err
			}
			_, err = os.Stdout.Write(data)
			return err
		},
	}
	cmd.Flags().StringVar(&ref, "ref", "", "ref to read (default: current branch)")
	return cmd
}

func newLogCmd() *cobra.Command {
	var branch string
	var limit int
	cmd := &cobra.Command{
		Use:   "log",
		Short: "Show commit history for a branch",
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
			if branch == "" {
				branch = w.Head.Branch
			}
			commits, total, err := e.client.Log(e.ctx, w.Config.ProjectID, branch, limit, 0)
			if err != nil {
				return err
			}
			if e.p.JSON {
				return e.p.EmitJSON(map[string]any{"branch": branch, "total": total, "commits": commits})
			}
			for _, c := range commits {
				e.p.Printf("%s  %s\n", short(c.SHA), c.Title)
				e.p.Printf("        %s · %s · %d file(s)\n", c.Author, c.Date, c.FilesChanged)
			}
			if len(commits) == 0 {
				e.p.Logf("no commits on %s yet\n", branch)
			}
			return nil
		},
	}
	cmd.Flags().StringVar(&branch, "branch", "", "branch (default: current)")
	cmd.Flags().IntVar(&limit, "limit", 20, "max commits to show")
	return cmd
}

func newBranchCmd() *cobra.Command {
	var from string
	var del bool
	cmd := &cobra.Command{
		Use:   "branch [name]",
		Short: "List branches, or create/delete one",
		Args:  cobra.MaximumNArgs(1),
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

			if len(args) == 0 {
				branches, err := e.client.ListBranches(e.ctx, pid)
				if err != nil {
					return err
				}
				if e.p.JSON {
					return e.p.EmitJSON(branches)
				}
				for _, b := range branches {
					marker := "  "
					if b.Name == w.Head.Branch {
						marker = "* "
					}
					e.p.Printf("%s%-24s %s\n", marker, b.Name, branchStatus(b))
				}
				return nil
			}

			name := args[0]
			if del {
				if err := e.client.DeleteBranch(e.ctx, pid, name); err != nil {
					return err
				}
				if e.p.JSON {
					return e.p.EmitJSON(map[string]any{"deleted": name})
				}
				e.p.Logf("Deleted branch %s\n", name)
				return nil
			}

			start := from
			if start == "" {
				start = w.Config.DefaultBranch
			}
			branches, err := e.client.CreateBranch(e.ctx, pid, name, start)
			if err != nil {
				return err
			}
			if e.p.JSON {
				return e.p.EmitJSON(branches)
			}
			e.p.Logf("Created branch %s from %s\n", name, start)
			return nil
		},
	}
	cmd.Flags().StringVar(&from, "from", "", "start point for a new branch (default: default branch)")
	cmd.Flags().BoolVar(&del, "delete", false, "delete the named branch")
	return cmd
}

// branchStatus renders the short flags shown after a branch name.
func branchStatus(b client.Branch) string {
	var parts []string
	if b.IsDefault {
		parts = append(parts, "default")
	}
	if b.IsProtected {
		parts = append(parts, "protected")
	}
	if !b.IsDefault {
		if b.Merged {
			parts = append(parts, "merged")
		} else {
			parts = append(parts, fmt.Sprintf("ahead %d, behind %d", b.Ahead, b.Behind))
		}
	}
	return strings.Join(parts, ", ")
}
