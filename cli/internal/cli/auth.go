package cli

import (
	"bufio"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/pkg/browser"
	"github.com/spf13/cobra"
	"golang.org/x/term"

	"github.com/spykeautomation/spyke/spykecore/client"
)

func newLoginCmd() *cobra.Command {
	var password bool
	var email string
	var noBrowser bool
	cmd := &cobra.Command{
		Use:   "login",
		Short: "Authenticate and store a token for this server",
		Long: "Sign in to the Spyke API. By default this opens your browser to approve\n" +
			"the sign-in (device flow). Use --password for a headless email+password\n" +
			"login (CI), or set $SPYKE_TOKEN to inject a token directly.",
		Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, args []string) error {
			e := newEnv()
			var (
				token string
				err   error
			)
			if password {
				token, err = passwordLogin(e, email)
			} else {
				token, err = deviceLogin(e, noBrowser)
			}
			if err != nil {
				return err
			}
			if err := e.store.Set(e.server, token); err != nil {
				return fmt.Errorf("saving credentials: %w", err)
			}
			e.client.Token = token
			u, _ := e.client.Me(e.ctx)
			if e.p.JSON {
				out := map[string]any{"server": e.server, "logged_in": true}
				if u != nil {
					out["user"] = u
				}
				return e.p.EmitJSON(out)
			}
			if u != nil {
				e.p.Logf("✓ Logged in to %s as %s\n", e.server, u.Name())
			} else {
				e.p.Logf("✓ Logged in to %s\n", e.server)
			}
			return nil
		},
	}
	cmd.Flags().BoolVar(&password, "password", false, "log in with email + password instead of the browser (CI/headless)")
	cmd.Flags().StringVar(&email, "email", "", "email for --password login (prompted if omitted)")
	cmd.Flags().BoolVar(&noBrowser, "no-browser", false, "don't open a browser; just print the URL to visit (SSH/headless)")
	return cmd
}

func passwordLogin(e *env, email string) (string, error) {
	reader := bufio.NewReader(os.Stdin)
	isTTY := term.IsTerminal(int(os.Stdin.Fd()))

	if email == "" {
		email = strings.TrimSpace(os.Getenv("SPYKE_EMAIL"))
	}
	if email == "" {
		e.p.Logf("Email: ")
		line, err := reader.ReadString('\n')
		if err != nil {
			return "", fmt.Errorf("reading email: %w", err)
		}
		email = strings.TrimSpace(line)
	}

	pw := os.Getenv("SPYKE_PASSWORD")
	if pw == "" {
		if isTTY {
			e.p.Logf("Password: ")
			b, err := term.ReadPassword(int(os.Stdin.Fd()))
			e.p.Logf("\n")
			if err != nil {
				return "", fmt.Errorf("reading password: %w", err)
			}
			pw = string(b)
		} else {
			// Headless/CI: read the password as a line from stdin.
			line, err := reader.ReadString('\n')
			if err != nil && line == "" {
				return "", fmt.Errorf("reading password from stdin: %w", err)
			}
			pw = line
		}
	}
	return e.client.Login(e.ctx, email, strings.TrimRight(pw, "\r\n"))
}

func deviceLogin(e *env, noBrowser bool) (string, error) {
	dc, err := e.client.RequestDeviceCode(e.ctx)
	if err != nil {
		return "", err
	}
	url := dc.VerificationURIComplete
	if url == "" {
		url = dc.VerificationURI
	}
	e.p.Logf("\nTo approve this sign-in, visit:\n  %s\n", url)
	e.p.Logf("Confirm this code matches what you see there: %s\n\n", dc.UserCode)
	if noBrowser {
		e.p.Logf("(open the URL above in any browser)\n")
	} else if err := browser.OpenURL(url); err != nil {
		e.p.Logf("(couldn't open the browser automatically — visit the URL above)\n")
	}

	interval := time.Duration(dc.PollInterval()) * time.Second
	expiry := dc.ExpiresIn
	if expiry < 60 {
		expiry = 600
	}
	deadline := time.Now().Add(time.Duration(expiry) * time.Second)

	e.p.Logf("Waiting for approval")
	for {
		if time.Now().After(deadline) {
			e.p.Logf("\n")
			return "", fmt.Errorf("login timed out before it was approved")
		}
		time.Sleep(interval)
		token, state, err := e.client.PollDeviceTokenOnce(e.ctx, dc.DeviceCode)
		if err != nil {
			e.p.Logf("\n")
			return "", err
		}
		switch state {
		case client.PollDone:
			e.p.Logf(" approved.\n")
			return token, nil
		case client.PollSlowDown:
			interval += 5 * time.Second
		}
		e.p.Logf(".")
	}
}

func newLogoutCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "logout",
		Short: "Remove the stored token for this server",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, args []string) error {
			e := newEnv()
			if err := e.store.Delete(e.server); err != nil {
				return err
			}
			if e.p.JSON {
				return e.p.EmitJSON(map[string]any{"server": e.server, "logged_in": false})
			}
			e.p.Logf("Logged out of %s\n", e.server)
			return nil
		},
	}
}

func newWhoamiCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "whoami",
		Short: "Show the authenticated user",
		Args:  cobra.NoArgs,
		RunE: func(cmd *cobra.Command, args []string) error {
			e := newEnv()
			if err := e.requireAuth(); err != nil {
				return err
			}
			u, err := e.client.Me(e.ctx)
			if err != nil {
				return err
			}
			if e.p.JSON {
				return e.p.EmitJSON(u)
			}
			org := u.Organization
			if org == "" {
				org = "(no organization)"
			}
			e.p.Printf("%s <%s>\n%s\n", u.Name(), u.Email, org)
			return nil
		},
	}
}
