// Package config holds CLI-wide defaults and environment-variable names that
// both the CLI front-end and the spykecore engine share.
package config

import (
	"os"
	"strings"
)

const (
	// DefaultServer is the production Spyke API base URL. The CLI always talks
	// to the API host (api.*), never the web app (app.*) — the web app is only
	// opened in a browser during `spyke login`.
	DefaultServer = "https://api.spykeautomation.com"

	// EnvServer overrides the server URL for a single invocation/session.
	EnvServer = "SPYKE_SERVER"

	// EnvToken injects a bearer token directly, bypassing the credential store.
	// Intended for CI/automation.
	EnvToken = "SPYKE_TOKEN"

	// UserAgent identifies the CLI on every request.
	UserAgent = "spyke-cli"
)

// ResolveServer picks the API base URL, in precedence order: an explicit flag
// value, then SPYKE_SERVER, then the compiled-in default. The result has any
// trailing slash trimmed.
func ResolveServer(flagValue string) string {
	v := strings.TrimSpace(flagValue)
	if v == "" {
		v = strings.TrimSpace(os.Getenv(EnvServer))
	}
	if v == "" {
		v = DefaultServer
	}
	return strings.TrimRight(v, "/")
}
