package workspace

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestPathMapping(t *testing.T) {
	cases := []struct {
		logical, upload, source, local string
	}{
		{"l5x/Line1", "Line1.L5X", "l5x/Line1/source.L5X", "Line1.L5X"},
		{"files/docs/io.csv", "docs/io.csv", "files/docs/io.csv", filepath.FromSlash("docs/io.csv")},
	}
	for _, c := range cases {
		if got := UploadName(c.logical); got != c.upload {
			t.Errorf("UploadName(%q)=%q want %q", c.logical, got, c.upload)
		}
		if got := RepoSourcePath(c.logical); got != c.source {
			t.Errorf("RepoSourcePath(%q)=%q want %q", c.logical, got, c.source)
		}
		got, ok := LocalPathFor(c.logical)
		if !ok || got != c.local {
			t.Errorf("LocalPathFor(%q)=%q,%v want %q,true", c.logical, got, ok, c.local)
		}
	}
	if got := LogicalForLocal("Line1.L5X"); got != "l5x/Line1" {
		t.Errorf("LogicalForLocal L5X = %q", got)
	}
	if got := LogicalForLocal(filepath.FromSlash("docs/io.csv")); got != "files/docs/io.csv" {
		t.Errorf("LogicalForLocal file = %q", got)
	}
	if got := LogicalForLocal("PUMP.l5x"); got != "l5x/PUMP" {
		t.Errorf("case-insensitive .l5x ext = %q", got)
	}
}

func TestValidateLogical(t *testing.T) {
	for _, l := range []string{"l5x/Line1", "l5x/Line 1", "files/docs/io.csv", "files/a.txt"} {
		if err := ValidateLogical(l); err != nil {
			t.Errorf("ValidateLogical(%q) unexpected error: %v", l, err)
		}
	}
	for _, l := range []string{"files/../x", "files/con/x", "l5x/a/b", "files/a*b.txt"} {
		if err := ValidateLogical(l); err == nil {
			t.Errorf("ValidateLogical(%q) expected an error", l)
		}
	}
}

func TestScanAndDiff(t *testing.T) {
	root := t.TempDir()
	mustWrite(t, filepath.Join(root, "A.L5X"), "controller")
	mustWrite(t, filepath.Join(root, "sub", "b.txt"), "hello")
	mustWrite(t, filepath.Join(root, Dir, "junk"), "ignore me") // under .spyke -> skipped

	working, err := Scan(root)
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := working["l5x/A"]; !ok {
		t.Errorf("missing l5x/A; keys=%v", keys(working))
	}
	if _, ok := working["files/sub/b.txt"]; !ok {
		t.Errorf("missing files/sub/b.txt; keys=%v", keys(working))
	}
	for k := range working {
		if strings.HasPrefix(k, "files/"+Dir) {
			t.Errorf(".spyke not skipped: %q", k)
		}
	}

	// Empty index: everything is added.
	if changes := Diff(Index{}, working); len(changes) != 2 {
		t.Fatalf("want 2 added, got %d: %v", len(changes), changes)
	}
	// One matches the baseline: only the other shows.
	idx := Index{"l5x/A": {SHA256: working["l5x/A"].SHA256}}
	changes := Diff(idx, working)
	if len(changes) != 1 || changes[0].Logical != "files/sub/b.txt" || changes[0].Status != "added" {
		t.Fatalf("unexpected diff: %v", changes)
	}
	// Baseline differs: modified.
	idx["l5x/A"] = IndexEntry{SHA256: "different"}
	if !hasChange(Diff(idx, working), "l5x/A", "modified") {
		t.Errorf("expected l5x/A modified")
	}
	// Missing from working tree: deleted.
	del := Diff(Index{"files/gone.txt": {SHA256: "x"}}, map[string]WorkingFile{})
	if len(del) != 1 || del[0].Status != "deleted" {
		t.Errorf("expected one deleted, got %v", del)
	}
}

func TestScanDetectsCollision(t *testing.T) {
	root := t.TempDir()
	mustWrite(t, filepath.Join(root, "Line.L5X"), "a")
	mustWrite(t, filepath.Join(root, "sub", "Line.l5x"), "b") // same stem -> same logical
	if _, err := Scan(root); err == nil {
		t.Errorf("expected a collision error for two files mapping to l5x/Line")
	}
}

func TestWorkspaceRoundTrip(t *testing.T) {
	root := t.TempDir()
	cfg := Config{ServerURL: "http://x", ProjectID: 7, ProjectSlug: "p", DefaultBranch: "main"}
	idx := Index{"files/a.txt": {SHA256: "h", Size: 3, SyncedSHA: "deadbeef"}}
	if _, err := Create(root, cfg, Head{Branch: "main", CommitSHA: "abc"}, idx); err != nil {
		t.Fatal(err)
	}
	sub := filepath.Join(root, "deep", "er")
	if err := os.MkdirAll(sub, 0o755); err != nil {
		t.Fatal(err)
	}
	w, err := Find(sub) // walks up to the .spyke root
	if err != nil {
		t.Fatal(err)
	}
	if w.Config.ProjectID != 7 || w.Head.CommitSHA != "abc" {
		t.Errorf("bad load: cfg=%+v head=%+v", w.Config, w.Head)
	}
	got, err := w.LoadIndex()
	if err != nil {
		t.Fatal(err)
	}
	if got["files/a.txt"].SyncedSHA != "deadbeef" {
		t.Errorf("index round-trip failed: %+v", got)
	}
}

func TestPendingRoundTrip(t *testing.T) {
	root := t.TempDir()
	w, err := Create(root, Config{ProjectID: 1}, Head{Branch: "main"}, Index{})
	if err != nil {
		t.Fatal(err)
	}
	seq, err := w.QueueCommit("msg", "desc", map[string][]byte{
		"files/a.txt": []byte("hi"),
		"l5x/Line":    []byte("ctrl"),
	})
	if err != nil {
		t.Fatal(err)
	}
	pend, err := w.ListPending()
	if err != nil {
		t.Fatal(err)
	}
	if len(pend) != 1 || pend[0].Seq != seq || len(pend[0].Files) != 2 {
		t.Fatalf("bad pending: %+v", pend)
	}
	for _, f := range pend[0].Files {
		b, err := os.ReadFile(pend[0].BlobPath(f))
		if err != nil || len(b) == 0 {
			t.Errorf("blob %s unreadable/empty: %v", f.Logical, err)
		}
		if f.Logical == "l5x/Line" && f.Upload != "Line.L5X" {
			t.Errorf("upload name for l5x = %q", f.Upload)
		}
	}
	if err := w.RemovePending(seq); err != nil {
		t.Fatal(err)
	}
	if pend, _ := w.ListPending(); len(pend) != 0 {
		t.Errorf("pending not removed: %+v", pend)
	}
}

func mustWrite(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
}

func hasChange(changes []Change, logical, status string) bool {
	for _, c := range changes {
		if c.Logical == logical && c.Status == status {
			return true
		}
	}
	return false
}

func keys(m map[string]WorkingFile) []string {
	var k []string
	for x := range m {
		k = append(k, x)
	}
	return k
}
