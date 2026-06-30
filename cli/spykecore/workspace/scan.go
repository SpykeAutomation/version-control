package workspace

import (
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

// WorkingFile is one file found in the working tree, keyed by its logical path.
type WorkingFile struct {
	Logical string // "l5x/<name>" or "files/<rel>"
	Local   string // path relative to the workspace root (OS separators)
	SHA256  string
	Size    int64
}

// Scan walks the working tree (skipping the .spyke metadata dir) and returns the
// current files keyed by logical path. If two files map to the same logical path
// (e.g. two L5X files with the same stem), the collision is reported as an error
// so the user can resolve it before committing.
func Scan(root string) (map[string]WorkingFile, error) {
	out := map[string]WorkingFile{}
	seen := map[string]string{} // logical -> first local path
	err := filepath.WalkDir(root, func(path string, d fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if d.IsDir() {
			if d.Name() == Dir {
				return filepath.SkipDir
			}
			return nil
		}
		rel, err := filepath.Rel(root, path)
		if err != nil {
			return err
		}
		data, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		logical := LogicalForLocal(rel)
		if first, dup := seen[logical]; dup {
			return fmt.Errorf("%q and %q both map to %q — rename one", first, rel, logical)
		}
		seen[logical] = rel
		out[logical] = WorkingFile{Logical: logical, Local: rel, SHA256: HashBytes(data), Size: int64(len(data))}
		return nil
	})
	if err != nil {
		return nil, err
	}
	return out, nil
}

// Change is one difference between the working tree and the index baseline.
type Change struct {
	Logical string `json:"path"`
	Status  string `json:"status"` // "added" | "modified" | "deleted"
}

// Diff compares the working tree against the index baseline. "deleted" entries
// are reported but cannot be pushed (the API has no delete) — callers warn.
func Diff(index Index, working map[string]WorkingFile) []Change {
	var changes []Change
	for logical, wf := range working {
		base, ok := index[logical]
		switch {
		case !ok:
			changes = append(changes, Change{logical, "added"})
		case base.SHA256 != wf.SHA256:
			changes = append(changes, Change{logical, "modified"})
		}
	}
	for logical := range index {
		if _, ok := working[logical]; !ok {
			changes = append(changes, Change{logical, "deleted"})
		}
	}
	sort.Slice(changes, func(i, j int) bool { return changes[i].Logical < changes[j].Logical })
	return changes
}

// --- upload-name validation (mirrors backend/vcs/project_repo.py) -----------

var safeComponent = regexp.MustCompile(`^[A-Za-z0-9 _.-]+$`)

var windowsReserved = func() map[string]bool {
	m := map[string]bool{"con": true, "prn": true, "aux": true, "nul": true}
	for i := 1; i <= 9; i++ {
		m[fmt.Sprintf("com%d", i)] = true
		m[fmt.Sprintf("lpt%d", i)] = true
	}
	return m
}()

const (
	maxFileDepth   = 20
	maxFilePathLen = 400
)

// ValidateLogical checks that a logical path's upload name will be accepted by
// the server, so the CLI can fail fast with a clear message instead of a 400.
func ValidateLogical(logical string) error {
	name := UploadName(logical)
	if strings.HasPrefix(logical, "l5x/") {
		stem := strings.TrimSuffix(strings.TrimPrefix(logical, "l5x/"), "/")
		if stem == "" || stem == "." || stem == ".." || !safeComponent.MatchString(stem) {
			return fmt.Errorf("unsafe L5X name %q (allowed: letters, digits, space, _ . -)", stem)
		}
		return nil
	}
	raw := strings.ReplaceAll(name, "\\", "/")
	parts := []string{}
	for _, p := range strings.Split(raw, "/") {
		if p == "" || p == "." {
			continue
		}
		parts = append(parts, p)
	}
	if len(parts) == 0 || len(parts) > maxFileDepth || len(raw) > maxFilePathLen {
		return fmt.Errorf("unsafe file path %q", name)
	}
	for _, p := range parts {
		if p == ".." || !safeComponent.MatchString(p) {
			return fmt.Errorf("unsafe file path component %q in %q", p, name)
		}
		if windowsReserved[strings.ToLower(p)] {
			return fmt.Errorf("reserved Windows name %q in %q", p, name)
		}
	}
	return nil
}

// UploadName is the multipart filename to send for a logical path so the server
// versions the same logical file: an L5X stem becomes "<name>.L5X"; a files/
// entry keeps its relative path.
func UploadName(logical string) string {
	if name, ok := strings.CutPrefix(logical, "l5x/"); ok {
		return strings.TrimSuffix(name, "/") + ".L5X"
	}
	if rel, ok := strings.CutPrefix(logical, "files/"); ok {
		return rel
	}
	return logical
}
