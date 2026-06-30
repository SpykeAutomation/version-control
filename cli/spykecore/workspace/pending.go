package workspace

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
)

// PendingFile records one file in a queued commit: its logical path, the
// multipart filename to upload it under, and the local blob holding the bytes
// snapshotted at commit time.
type PendingFile struct {
	Logical string `json:"logical"`
	Upload  string `json:"upload"`
	Blob    string `json:"blob"` // filename under the commit's blobs/ dir
}

// PendingCommit is a commit that has been made locally but not yet pushed. Its
// file bytes are snapshotted into blobs/ so later edits to the working tree
// can't corrupt what gets uploaded.
type PendingCommit struct {
	Seq         int           `json:"seq"`
	Title       string        `json:"title"`
	Description string        `json:"description"`
	Files       []PendingFile `json:"files"`

	dir string // on-disk directory; not serialized
}

// BlobPath returns the absolute path to a pending file's snapshotted bytes.
func (pc *PendingCommit) BlobPath(f PendingFile) string {
	return filepath.Join(pc.dir, "blobs", f.Blob)
}

// QueueCommit writes a new pending commit: meta.json plus a blob per file. files
// maps logical path -> bytes. Returns the assigned sequence number.
func (w *Workspace) QueueCommit(title, description string, files map[string][]byte) (int, error) {
	if len(files) == 0 {
		return 0, fmt.Errorf("no files to commit")
	}
	seq, err := w.nextSeq()
	if err != nil {
		return 0, err
	}
	dir := filepath.Join(w.PendingDir(), strconv.Itoa(seq))
	if err := os.MkdirAll(filepath.Join(dir, "blobs"), 0o755); err != nil {
		return 0, err
	}
	pc := PendingCommit{Seq: seq, Title: title, Description: description, dir: dir}

	// Stable order so blob names are deterministic.
	logicals := make([]string, 0, len(files))
	for l := range files {
		logicals = append(logicals, l)
	}
	sort.Strings(logicals)
	for i, logical := range logicals {
		blob := strconv.Itoa(i)
		if err := os.WriteFile(filepath.Join(dir, "blobs", blob), files[logical], 0o644); err != nil {
			return 0, err
		}
		pc.Files = append(pc.Files, PendingFile{Logical: logical, Upload: UploadName(logical), Blob: blob})
	}
	if err := writeJSON(filepath.Join(dir, "meta.json"), pc); err != nil {
		return 0, err
	}
	return seq, nil
}

// ListPending returns the queued commits in push order (ascending seq).
func (w *Workspace) ListPending() ([]PendingCommit, error) {
	root := w.PendingDir()
	entries, err := os.ReadDir(root)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	var out []PendingCommit
	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		dir := filepath.Join(root, e.Name())
		var pc PendingCommit
		if err := readJSON(filepath.Join(dir, "meta.json"), &pc); err != nil {
			return nil, fmt.Errorf("reading pending commit %s: %w", e.Name(), err)
		}
		pc.dir = dir
		out = append(out, pc)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Seq < out[j].Seq })
	return out, nil
}

// RemovePending deletes a pending commit (after a successful push).
func (w *Workspace) RemovePending(seq int) error {
	return os.RemoveAll(filepath.Join(w.PendingDir(), strconv.Itoa(seq)))
}

func (w *Workspace) nextSeq() (int, error) {
	existing, err := w.ListPending()
	if err != nil {
		return 0, err
	}
	max := 0
	for _, pc := range existing {
		if pc.Seq > max {
			max = pc.Seq
		}
	}
	return max + 1, nil
}
