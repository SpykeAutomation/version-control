// Package workspace manages the local .spyke directory that binds a folder to a
// remote project — the git-like part of the CLI. It records which project the
// folder tracks, the current branch + last-synced commit, and a content-hash
// baseline used to detect local changes. There is no local commit graph: a
// commit exists only once uploaded, so this is a sync baseline, not history.
package workspace

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// Dir is the per-workspace metadata directory (analogous to .git).
const Dir = ".spyke"

// Config binds the folder to a remote project.
type Config struct {
	ServerURL     string `json:"server_url"`
	ProjectID     int    `json:"project_id"`
	ProjectSlug   string `json:"project_slug"`
	DefaultBranch string `json:"default_branch"`
}

// Head is the checked-out branch and the server commit it was last synced to.
type Head struct {
	Branch    string `json:"branch"`
	CommitSHA string `json:"commit_sha"`
}

// IndexEntry is the synced baseline for one logical file (keyed by logical path
// in Index): the content hash + size at last sync, and the commit it came from.
type IndexEntry struct {
	SHA256    string `json:"sha256"`
	Size      int64  `json:"size"`
	SyncedSHA string `json:"synced_sha"`
}

// Index maps a logical repo path ("l5x/<name>" or "files/<rel>") to its baseline.
type Index map[string]IndexEntry

// Workspace is an opened .spyke workspace rooted at Root.
type Workspace struct {
	Root   string
	Config Config
	Head   Head
}

func metaDir(root string) string  { return filepath.Join(root, Dir) }
func configPath(root string) string { return filepath.Join(metaDir(root), "config.json") }
func headPath(root string) string   { return filepath.Join(metaDir(root), "HEAD.json") }
func indexPath(root string) string  { return filepath.Join(metaDir(root), "index.json") }

// PendingDir is where queued (committed-but-unpushed) commits live.
func (w *Workspace) PendingDir() string { return filepath.Join(metaDir(w.Root), "pending") }

// Find walks up from start (default: CWD) looking for a .spyke directory and
// opens it. Returns a friendly error if none is found.
func Find(start string) (*Workspace, error) {
	if start == "" {
		cwd, err := os.Getwd()
		if err != nil {
			return nil, err
		}
		start = cwd
	}
	dir, err := filepath.Abs(start)
	if err != nil {
		return nil, err
	}
	for {
		if info, err := os.Stat(metaDir(dir)); err == nil && info.IsDir() {
			return open(dir)
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			return nil, fmt.Errorf("not a spyke workspace (no %s found here or in any parent) — run `spyke clone` first", Dir)
		}
		dir = parent
	}
}

func open(root string) (*Workspace, error) {
	w := &Workspace{Root: root}
	if err := readJSON(configPath(root), &w.Config); err != nil {
		return nil, fmt.Errorf("reading workspace config: %w", err)
	}
	if err := readJSON(headPath(root), &w.Head); err != nil {
		return nil, fmt.Errorf("reading workspace HEAD: %w", err)
	}
	return w, nil
}

// Create initializes a new .spyke workspace at root. root is created if needed;
// it must not already contain a .spyke directory.
func Create(root string, cfg Config, head Head, index Index) (*Workspace, error) {
	if err := os.MkdirAll(metaDir(root), 0o755); err != nil {
		return nil, err
	}
	w := &Workspace{Root: root, Config: cfg, Head: head}
	if err := w.SaveConfig(); err != nil {
		return nil, err
	}
	if err := w.SaveHead(); err != nil {
		return nil, err
	}
	if index == nil {
		index = Index{}
	}
	if err := w.SaveIndex(index); err != nil {
		return nil, err
	}
	return w, nil
}

func (w *Workspace) SaveConfig() error { return writeJSON(configPath(w.Root), w.Config) }
func (w *Workspace) SaveHead() error   { return writeJSON(headPath(w.Root), w.Head) }

func (w *Workspace) LoadIndex() (Index, error) {
	idx := Index{}
	if err := readJSON(indexPath(w.Root), &idx); err != nil {
		if os.IsNotExist(err) {
			return Index{}, nil
		}
		return nil, err
	}
	return idx, nil
}

func (w *Workspace) SaveIndex(idx Index) error { return writeJSON(indexPath(w.Root), idx) }

// --- logical <-> local path mapping -----------------------------------------

// LocalPathFor returns the on-disk path (relative to the workspace root, using
// the OS separator) for a logical repo path. L5X files live at the root as
// "<name>.L5X"; other files keep their "files/<rel>" layout.
func LocalPathFor(logical string) (string, bool) {
	if name, ok := strings.CutPrefix(logical, "l5x/"); ok {
		name = strings.TrimSuffix(name, "/")
		if name == "" {
			return "", false
		}
		return name + ".L5X", true
	}
	if rel, ok := strings.CutPrefix(logical, "files/"); ok {
		if rel == "" {
			return "", false
		}
		return filepath.FromSlash(rel), true
	}
	return "", false
}

// LogicalForLocal maps a working-tree path (relative to root, any separator) to
// its logical repo path: a *.l5x file collapses to "l5x/<stem>"; anything else
// becomes "files/<rel>".
func LogicalForLocal(rel string) string {
	slash := filepath.ToSlash(rel)
	if strings.EqualFold(filepath.Ext(slash), ".l5x") {
		stem := strings.TrimSuffix(filepath.Base(slash), filepath.Ext(slash))
		return "l5x/" + stem
	}
	return "files/" + slash
}

// RepoSourcePath returns the repo path to download a logical file's original
// bytes from: an L5X's "l5x/<name>/source.L5X", or the files/ path verbatim.
func RepoSourcePath(logical string) string {
	if name, ok := strings.CutPrefix(logical, "l5x/"); ok {
		return "l5x/" + strings.TrimSuffix(name, "/") + "/source.L5X"
	}
	return logical
}

// --- hashing ----------------------------------------------------------------

// HashBytes returns the hex SHA-256 of b (the content-identity used in Index).
func HashBytes(b []byte) string {
	sum := sha256.Sum256(b)
	return hex.EncodeToString(sum[:])
}

// --- small JSON helpers -----------------------------------------------------

func readJSON(path string, out any) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return json.Unmarshal(data, out)
}

func writeJSON(path string, v any) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	data, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, append(data, '\n'), 0o644)
}
