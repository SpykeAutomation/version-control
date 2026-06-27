//go:build !windows

package creds

import (
	"encoding/json"
	"os"
	"path/filepath"
)

// fileStore keeps tokens in a 0600 JSON file under the user config dir. Used for
// development on macOS/Linux; the shipped Windows build uses the Credential
// Manager instead.
type fileStore struct{ path string }

func newStore() Store {
	dir, err := os.UserConfigDir()
	if err != nil || dir == "" {
		dir = filepath.Join(os.Getenv("HOME"), ".config")
	}
	return &fileStore{path: filepath.Join(dir, "spyke", "credentials.json")}
}

func (s *fileStore) load() (map[string]string, error) {
	m := map[string]string{}
	data, err := os.ReadFile(s.path)
	if err != nil {
		if os.IsNotExist(err) {
			return m, nil
		}
		return nil, err
	}
	if len(data) == 0 {
		return m, nil
	}
	if err := json.Unmarshal(data, &m); err != nil {
		return nil, err
	}
	return m, nil
}

func (s *fileStore) save(m map[string]string) error {
	if err := os.MkdirAll(filepath.Dir(s.path), 0o700); err != nil {
		return err
	}
	data, err := json.MarshalIndent(m, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(s.path, data, 0o600)
}

func (s *fileStore) Get(server string) (string, error) {
	m, err := s.load()
	if err != nil {
		return "", err
	}
	return m[targetName(server)], nil
}

func (s *fileStore) Set(server, token string) error {
	m, err := s.load()
	if err != nil {
		return err
	}
	m[targetName(server)] = token
	return s.save(m)
}

func (s *fileStore) Delete(server string) error {
	m, err := s.load()
	if err != nil {
		return err
	}
	delete(m, targetName(server))
	return s.save(m)
}
