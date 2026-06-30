// Package creds stores the Spyke bearer token per server URL. On Windows it uses
// the Credential Manager (DPAPI-backed); on other platforms (dev) it falls back
// to a 0600 file under the user config dir. SPYKE_TOKEN overrides any store.
package creds

import (
	"os"
	"strings"

	"github.com/spykeautomation/spyke/spykecore/config"
)

// Store persists one bearer token per server URL.
type Store interface {
	Get(server string) (string, error)
	Set(server, token string) error
	Delete(server string) error
}

// New returns the platform credential store.
func New() Store { return newStore() }

// Resolve returns the effective token for server: SPYKE_TOKEN env first, then
// the store. An empty string means "not logged in".
func Resolve(s Store, server string) string {
	if t := strings.TrimSpace(os.Getenv(config.EnvToken)); t != "" {
		return t
	}
	if t, err := s.Get(server); err == nil {
		return strings.TrimSpace(t)
	}
	return ""
}

// targetName is the per-server key used by both backends.
func targetName(server string) string { return "spyke:" + server }
