//go:build windows

package creds

import "github.com/danieljoos/wincred"

// winStore stores the token as a generic credential in the Windows Credential
// Manager (encrypted at rest per-user via DPAPI), keyed by "spyke:<server>".
type winStore struct{}

func newStore() Store { return &winStore{} }

func (s *winStore) Get(server string) (string, error) {
	cred, err := wincred.GetGenericCredential(targetName(server))
	if err != nil {
		// Treat "not found" as simply not logged in.
		return "", nil
	}
	return string(cred.CredentialBlob), nil
}

func (s *winStore) Set(server, token string) error {
	cred := wincred.NewGenericCredential(targetName(server))
	cred.UserName = "spyke"
	cred.CredentialBlob = []byte(token)
	return cred.Write()
}

func (s *winStore) Delete(server string) error {
	cred, err := wincred.GetGenericCredential(targetName(server))
	if err != nil {
		return nil // already absent
	}
	return cred.Delete()
}
