package cli

import (
	"context"
	"strconv"

	"github.com/spf13/cobra"

	"github.com/spykeautomation/spyke/spykecore/client"
	"github.com/spykeautomation/spyke/spykecore/workspace"
)

func newPRCmd() *cobra.Command {
	pr := &cobra.Command{
		Use:   "pr",
		Short: "Open, review, and merge pull requests",
	}
	pr.AddCommand(
		prCreateCmd(), prListCmd(), prViewCmd(), prDiffCmd(),
		prReviewCmd("approve", "Record your approval", (*client.Client).ApprovePull),
		prReviewCmd("request-changes", "Request changes", (*client.Client).RequestChangesPull),
		prMergeCmd(), prCommentCmd(),
	)
	return pr
}

// prNumber parses a PR number argument.
func prNumber(arg string) (int, error) {
	n, err := strconv.Atoi(arg)
	if err != nil {
		return 0, usageErr("pull request number must be an integer: %q", arg)
	}
	return n, nil
}

func prCreateCmd() *cobra.Command {
	var from, into, title, desc string
	c := &cobra.Command{
		Use:   "create",
		Short: "Open a pull request (defaults --from to the current branch)",
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
			if from == "" {
				from = w.Head.Branch
			}
			if title == "" {
				return usageErr("a title is required (-t)")
			}
			p, err := e.client.CreatePull(e.ctx, w.Config.ProjectID, client.PullCreate{
				Title: title, Description: desc, SourceBranch: from, TargetBranch: into,
			})
			if err != nil {
				return err
			}
			if e.p.JSON {
				return e.p.EmitJSON(p)
			}
			e.p.Logf("Opened PR #%d: %s (%s → %s)\n", p.Number, p.Title, p.SourceBranch, p.TargetBranch)
			return nil
		},
	}
	c.Flags().StringVar(&from, "from", "", "source branch (default: current branch)")
	c.Flags().StringVar(&into, "into", "main", "target branch")
	c.Flags().StringVarP(&title, "title", "t", "", "PR title (required)")
	c.Flags().StringVarP(&desc, "description", "d", "", "PR description")
	return c
}

func prListCmd() *cobra.Command {
	var status string
	c := &cobra.Command{
		Use:   "list",
		Short: "List pull requests",
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
			pulls, total, err := e.client.ListPulls(e.ctx, w.Config.ProjectID, status, 50, 0)
			if err != nil {
				return err
			}
			if e.p.JSON {
				return e.p.EmitJSON(map[string]any{"total": total, "pulls": pulls})
			}
			for _, p := range pulls {
				e.p.Printf("#%-4d %-7s %s (%s → %s)  %d/%d approvals\n",
					p.Number, p.Status, p.Title, p.SourceBranch, p.TargetBranch, p.Approvals, p.RequiredApprovals)
			}
			if len(pulls) == 0 {
				e.p.Logf("no pull requests\n")
			}
			return nil
		},
	}
	c.Flags().StringVar(&status, "status", "", "filter by status: open|merged|closed")
	return c
}

func prViewCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "view <number>",
		Short: "Show a pull request",
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
			n, err := prNumber(args[0])
			if err != nil {
				return err
			}
			p, err := e.client.GetPull(e.ctx, w.Config.ProjectID, n)
			if err != nil {
				return err
			}
			if e.p.JSON {
				return e.p.EmitJSON(p)
			}
			e.p.Printf("#%d %s\n", p.Number, p.Title)
			e.p.Printf("%s → %s · %s · by %s\n", p.SourceBranch, p.TargetBranch, p.Status, p.Author.Name())
			if p.Description != "" {
				e.p.Printf("\n%s\n", p.Description)
			}
			e.p.Printf("\nApprovals: %d/%d (approved: %t)\n", p.Approvals, p.RequiredApprovals, p.Approved)
			return nil
		},
	}
}

func prDiffCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "diff <number>",
		Short: "List the files a pull request would change",
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
			n, err := prNumber(args[0])
			if err != nil {
				return err
			}
			m, err := e.client.PullDiffManifest(e.ctx, w.Config.ProjectID, n)
			if err != nil {
				return err
			}
			if e.p.JSON {
				return e.p.EmitJSON(m)
			}
			for _, f := range m.Files {
				e.p.Printf("%-9s %s\n", f.Change, f.Path)
			}
			if len(m.Files) == 0 {
				e.p.Logf("no file changes\n")
			}
			return nil
		},
	}
}

// prReviewCmd builds the approve / request-changes subcommands, which share a
// shape and differ only by the client method they call.
func prReviewCmd(use, short string, fn func(*client.Client, context.Context, int, int) (*client.Pull, error)) *cobra.Command {
	return &cobra.Command{
		Use:   use + " <number>",
		Short: short,
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
			n, err := prNumber(args[0])
			if err != nil {
				return err
			}
			p, err := fn(e.client, e.ctx, w.Config.ProjectID, n)
			if err != nil {
				return err
			}
			if e.p.JSON {
				return e.p.EmitJSON(p)
			}
			e.p.Logf("Recorded your %s on PR #%d (%d/%d approvals)\n", use, n, p.Approvals, p.RequiredApprovals)
			return nil
		},
	}
}

func prMergeCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "merge <number>",
		Short: "Merge a pull request",
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
			n, err := prNumber(args[0])
			if err != nil {
				return err
			}
			res, err := e.client.MergePull(e.ctx, w.Config.ProjectID, n)
			if err != nil {
				return err
			}
			if e.p.JSON {
				return e.p.EmitJSON(res)
			}
			if res.Status == "conflict" {
				e.p.Logf("Merge conflict — %s\n", res.Message)
				for _, f := range res.Conflicts {
					e.p.Logf("  %s\n", f)
				}
				return nil // not an error: the PR stays open to resolve
			}
			e.p.Logf("Merged PR #%d → %s\n", n, short(res.MergeSHA))
			return nil
		},
	}
}

func prCommentCmd() *cobra.Command {
	var body string
	c := &cobra.Command{
		Use:   "comment <number>",
		Short: "Add a comment to a pull request",
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
			n, err := prNumber(args[0])
			if err != nil {
				return err
			}
			if body == "" {
				return usageErr("a comment body is required (-m)")
			}
			cm, err := e.client.AddComment(e.ctx, w.Config.ProjectID, n, body, nil)
			if err != nil {
				return err
			}
			if e.p.JSON {
				return e.p.EmitJSON(cm)
			}
			e.p.Logf("Commented on PR #%d\n", n)
			return nil
		},
	}
	c.Flags().StringVarP(&body, "message", "m", "", "comment body (required)")
	return c
}
