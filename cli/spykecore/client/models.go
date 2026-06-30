package client

import "encoding/json"

// These mirror the JSON shapes in backend/README.md ("Response shapes") and
// backend/app/schemas.py. Dates are kept as ISO-8601 strings (the server emits
// them that way) so the CLI/GUI can format them without a parse dependency.

// User is an account as returned by /auth/me and embedded in other shapes.
type User struct {
	ID           int    `json:"id"`
	Email        string `json:"email"`
	FirstName    string `json:"first_name"`
	LastName     string `json:"last_name"`
	Organization string `json:"organization"`
	Avatar       string `json:"avatar"`
}

// Name is the user's display name ("First Last"), falling back to the email.
func (u User) Name() string {
	full := u.FirstName
	if u.LastName != "" {
		if full != "" {
			full += " "
		}
		full += u.LastName
	}
	if full == "" {
		return u.Email
	}
	return full
}

// Project is a version-controlled project.
type Project struct {
	ID          int      `json:"id"`
	Name        string   `json:"name"`
	Slug        string   `json:"slug"`
	Description string   `json:"description"`
	Owner       User     `json:"owner"`
	YourRole    string   `json:"your_role"`
	CreatedAt   string   `json:"created_at"`
	Branches    []string `json:"branches"`
}

// Commit is one commit's metadata (a server-side Git commit).
type Commit struct {
	SHA          string `json:"sha"`
	Title        string `json:"title"`
	Description  string `json:"description"`
	Author       string `json:"author"`
	Date         string `json:"date"`
	Branch       string `json:"branch"`
	FilesChanged int    `json:"files_changed"`
}

// CommitResult is returned by an upload (the created commit).
type CommitResult struct {
	SHA    string `json:"sha"`
	Branch string `json:"branch"`
	Title  string `json:"title"`
}

// Branch is an enriched branch view.
type Branch struct {
	Name              string  `json:"name"`
	IsDefault         bool    `json:"is_default"`
	IsProtected       bool    `json:"is_protected"`
	RequiredApprovals int     `json:"required_approvals"`
	LatestCommit      *Commit `json:"latest_commit"`
	Ahead             int     `json:"ahead"`
	Behind            int     `json:"behind"`
	Merged            bool    `json:"merged"`
}

// FileEntry is one logical file present at a ref.
type FileEntry struct {
	Path       string `json:"path"` // "l5x/<name>" or "files/<nested/path>"
	Kind       string `json:"kind"` // "l5x" | "file"
	Size       int64  `json:"size"`
	ModifiedBy string `json:"modified_by"`
	ModifiedAt string `json:"modified_at"`
}

// FileListing is the project's files at a ref.
type FileListing struct {
	Files []FileEntry `json:"files"`
}

// ChangedFile is one entry of a diff manifest.
type ChangedFile struct {
	Path   string   `json:"path"`
	Kind   string   `json:"kind"`
	Change string   `json:"change"` // "added" | "modified" | "removed"
	Views  []string `json:"views"`
}

// DiffManifest lists the files that differ between two refs.
type DiffManifest struct {
	Files []ChangedFile `json:"files"`
}

// TextDiff is a unified line diff of a non-L5X file (nil Unified == binary).
type TextDiff struct {
	Path    string  `json:"path"`
	Binary  bool    `json:"binary"`
	Unified *string `json:"unified"`
}

// Review is one cast verdict on a pull request.
type Review struct {
	User      User   `json:"user"`
	State     string `json:"state"` // "approved" | "changes_requested"
	CreatedAt string `json:"created_at"`
}

// Pull is a pull request.
type Pull struct {
	Number            int      `json:"number"`
	Title             string   `json:"title"`
	Description       string   `json:"description"`
	SourceBranch      string   `json:"source_branch"`
	TargetBranch      string   `json:"target_branch"`
	Status            string   `json:"status"` // "open" | "merged" | "closed"
	Author            User     `json:"author"`
	MergeSHA          string   `json:"merge_sha"`
	CreatedAt         string   `json:"created_at"`
	UpdatedAt         string   `json:"updated_at"`
	Reviewers         []User   `json:"reviewers"`
	Reviews           []Review `json:"reviews"`
	RequiredApprovals int      `json:"required_approvals"`
	Approvals         int      `json:"approvals"`
	Approved          bool     `json:"approved"`
}

// Mergeability is the conflict dry-run + approval gate for a PR.
type Mergeability struct {
	Mergeable         bool     `json:"mergeable"`
	Conflicts         []string `json:"conflicts"`
	Approvals         int      `json:"approvals"`
	RequiredApprovals int      `json:"required_approvals"`
	Approved          bool     `json:"approved"`
	CanMerge          bool     `json:"can_merge"`
}

// MergeResult is the outcome of a merge attempt. A "conflict" status is a
// normal 200 response, not an error.
type MergeResult struct {
	Status    string   `json:"status"` // "merged" | "conflict"
	Message   string   `json:"message"`
	MergeSHA  string   `json:"merge_sha"`
	Conflicts []string `json:"conflicts"`
}

// Comment is a PR comment.
type Comment struct {
	ID       int    `json:"id"`
	Author   User   `json:"author"`
	Body     string `json:"body"`
	Resolved bool   `json:"resolved"`
	ParentID *int   `json:"parent_id"`
	CreatedAt string `json:"created_at"`
}

// Tag is a tag / release.
type Tag struct {
	Name      string  `json:"name"`
	SHA       string  `json:"sha"`
	Message   string  `json:"message"`
	Tagger    string  `json:"tagger"`
	Date      string  `json:"date"`
	Annotated bool    `json:"annotated"`
	Commit    *Commit `json:"commit"`
}

// tokenOut is the /auth/login (and device token) response.
type tokenOut struct {
	AccessToken string `json:"access_token"`
	TokenType   string `json:"token_type"`
}

// DeviceCodeResponse is returned by POST /auth/device/code (RFC 8628 §3.2).
type DeviceCodeResponse struct {
	DeviceCode              string `json:"device_code"`
	UserCode                string `json:"user_code"`
	VerificationURI         string `json:"verification_uri"`
	VerificationURIComplete string `json:"verification_uri_complete"`
	Interval                int    `json:"interval"`
	ExpiresIn               int    `json:"expires_in"`
}

// PollInterval is the device-token poll cadence, defaulting to 5s per RFC 8628
// when the server omits or under-specifies it.
func (d DeviceCodeResponse) PollInterval() int {
	if d.Interval < 1 {
		return 5
	}
	return d.Interval
}

// rawMessage is a tiny alias so command code can pass through opaque JSON
// (e.g. a ChangeSet or LadderDocument) to --json output without modeling it.
type RawJSON = json.RawMessage
