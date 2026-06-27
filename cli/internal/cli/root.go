// Package cli is the thin Cobra front-end over the spykecore engine. Commands
// parse arguments, call the engine, and render via internal/output. All real
// logic lives in spykecore so a GUI can drive the same engine.
package cli

import (
	"context"
	"errors"
	"os"

	"github.com/spf13/cobra"

	"github.com/spykeautomation/spyke/internal/output"
	"github.com/spykeautomation/spyke/spykecore/client"
	"github.com/spykeautomation/spyke/spykecore/config"
	"github.com/spykeautomation/spyke/spykecore/creds"
)

// version is overridable at build time with -ldflags "-X ...cli.version=...".
var version = "dev"

var (
	flagServer string
	flagJSON   bool
	flagChdir  string
)

// Execute builds the root command, runs it, and maps any error to a stable exit
// code (cobra's own error/usage printing is silenced so we control output).
func Execute() {
	root := newRootCmd()
	err := root.Execute()
	if err == nil {
		return
	}
	os.Exit(renderError(printer(), err))
}

func newRootCmd() *cobra.Command {
	root := &cobra.Command{
		Use:           "spyke",
		Short:         "Spyke — git-like version control for PLC projects",
		Long:          "spyke is a git-like CLI for the Spyke version-control platform.\nClone a project, edit L5X files, then status/commit/push and open pull requests.",
		Version:       version,
		SilenceErrors: true,
		SilenceUsage:  true,
		PersistentPreRunE: func(cmd *cobra.Command, args []string) error {
			if flagChdir != "" {
				return os.Chdir(flagChdir)
			}
			return nil
		},
	}
	pf := root.PersistentFlags()
	pf.StringVar(&flagServer, "server", "", "Spyke API base URL (default "+config.DefaultServer+", or $SPYKE_SERVER)")
	pf.BoolVar(&flagJSON, "json", false, "emit machine-readable JSON to stdout")
	pf.StringVarP(&flagChdir, "chdir", "C", "", "run as if spyke was started in <dir>")

	root.AddCommand(
		newLoginCmd(),
		newLogoutCmd(),
		newWhoamiCmd(),
		newCreateCmd(),
		newCloneCmd(),
		newStatusCmd(),
		newCommitCmd(),
		newPushCmd(),
		newPullCmd(),
		newCheckoutCmd(),
		newFilesCmd(),
		newCatCmd(),
		newLogCmd(),
		newBranchCmd(),
		newDiffCmd(),
		newPRCmd(),
		newTagCmd(),
	)
	return root
}

func printer() *output.Printer {
	return &output.Printer{JSON: flagJSON, Out: os.Stdout, Err: os.Stderr}
}

// env bundles the per-command dependencies: a configured API client, the
// credential store, the resolved server, and a printer.
type env struct {
	ctx    context.Context
	client *client.Client
	store  creds.Store
	server string
	p      *output.Printer
}

func newEnv() *env {
	server := config.ResolveServer(flagServer)
	store := creds.New()
	token := creds.Resolve(store, server)
	return &env{
		ctx:    context.Background(),
		client: client.New(server, token),
		store:  store,
		server: server,
		p:      printer(),
	}
}

// requireAuth returns a 401-style error if there is no token, so callers fail
// with the same shape (and exit code) as a real expired-token response.
func (e *env) requireAuth() error {
	if e.client.Token == "" {
		return &client.APIError{Status: 401, Code: client.CodeAuth, Message: "not logged in — run `spyke login`"}
	}
	return nil
}

// renderError prints err (JSON envelope or human line) and returns its exit code.
func renderError(p *output.Printer, err error) int {
	var ue *usageError
	if errors.As(err, &ue) {
		p.EmitError("usage", 0, ue.Error())
		return output.ExitUsage
	}
	if apiErr, ok := client.AsAPIError(err); ok {
		p.EmitError(apiErr.Code, apiErr.Status, apiErr.Message)
		return exitForCode(apiErr.Code)
	}
	p.EmitError(client.CodeOther, 0, err.Error())
	return output.ExitError
}

func exitForCode(code string) int {
	switch code {
	case client.CodeAuth, client.CodeForbidden:
		return output.ExitAuth
	case client.CodeConflict:
		return output.ExitConflict
	case client.CodeNotFound:
		return output.ExitNotFound
	case client.CodeQuota:
		return output.ExitQuota
	case client.CodeTooLarge:
		return output.ExitTooLarge
	default:
		return output.ExitError
	}
}
