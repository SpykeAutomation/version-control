package cli

import (
	"strings"

	"github.com/spf13/cobra"

	"github.com/spykeautomation/spyke/spykecore/client"
	"github.com/spykeautomation/spyke/spykecore/workspace"
)

func newDiffCmd() *cobra.Command {
	var ladder bool
	cmd := &cobra.Command{
		Use:   "diff <base> <head> [path]",
		Short: "Diff two refs: changed-file manifest, or one file's diff",
		Long: "With two refs, lists the files that differ. With a path (from `spyke diff`),\n" +
			"shows that file's diff: a semantic changeset for an L5X (l5x/<name>), or a\n" +
			"unified text diff for any other file (files/<path>). <ref> is a branch, SHA,\n" +
			"or expression like main~1.",
		Args: cobra.RangeArgs(2, 3),
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
			base, head := args[0], args[1]

			if len(args) == 2 {
				m, err := e.client.DiffManifest(e.ctx, pid, base, head)
				if err != nil {
					return err
				}
				if e.p.JSON {
					return e.p.EmitJSON(m)
				}
				if len(m.Files) == 0 {
					e.p.Logf("no differences between %s and %s\n", base, head)
					return nil
				}
				for _, f := range m.Files {
					e.p.Printf("%-9s %s\n", f.Change, f.Path)
				}
				return nil
			}

			path := args[2]
			if strings.HasPrefix(path, "files/") {
				td, err := e.client.TextDiff(e.ctx, pid, base, head, path)
				if err != nil {
					return err
				}
				if e.p.JSON {
					return e.p.EmitJSON(td)
				}
				if td.Binary {
					e.p.Logf("%s is binary — content changed (use `spyke cat` to download)\n", path)
					return nil
				}
				if td.Unified != nil {
					e.p.Printf("%s", *td.Unified)
				}
				return nil
			}

			// L5X: semantic changeset (or the drawable ladder diff).
			var raw client.RawJSON
			if ladder {
				raw, err = e.client.LadderRaw(e.ctx, pid, base, head, path)
			} else {
				raw, err = e.client.ChangesetRaw(e.ctx, pid, base, head, path)
			}
			if err != nil {
				return err
			}
			return e.p.EmitRawJSON(raw)
		},
	}
	cmd.Flags().BoolVar(&ladder, "ladder", false, "show the ladder-diagram diff instead of the changeset (L5X only)")
	return cmd
}
