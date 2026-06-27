package cli

import (
	"github.com/spf13/cobra"

	"github.com/spykeautomation/spyke/spykecore/workspace"
)

func newTagCmd() *cobra.Command {
	var ref, message string
	cmd := &cobra.Command{
		Use:   "tag [name]",
		Short: "List tags/releases, or cut a new one",
		Long:  "With no name, lists tags (newest first). With a name, cuts a tag at --ref;\na non-empty -m makes an annotated release with notes.",
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
				tags, total, err := e.client.ListTags(e.ctx, pid, 50, 0)
				if err != nil {
					return err
				}
				if e.p.JSON {
					return e.p.EmitJSON(map[string]any{"total": total, "tags": tags})
				}
				for _, t := range tags {
					kind := "lightweight"
					if t.Annotated {
						kind = "release"
					}
					e.p.Printf("%-18s %s  %s\n", t.Name, short(t.SHA), kind)
				}
				if len(tags) == 0 {
					e.p.Logf("no tags\n")
				}
				return nil
			}

			name := args[0]
			if ref == "" {
				ref = "main"
			}
			t, err := e.client.CreateTag(e.ctx, pid, name, ref, message)
			if err != nil {
				return err
			}
			if e.p.JSON {
				return e.p.EmitJSON(t)
			}
			e.p.Logf("Created tag %s at %s\n", t.Name, ref)
			return nil
		},
	}
	cmd.Flags().StringVar(&ref, "ref", "", "ref to tag (default: main)")
	cmd.Flags().StringVarP(&message, "message", "m", "", "release notes (makes an annotated release)")
	return cmd
}
