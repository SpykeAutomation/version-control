package client

import (
	"context"
	"fmt"
	"net/url"
	"strconv"
)

// --- projects ---------------------------------------------------------------

func (c *Client) ListProjects(ctx context.Context) ([]Project, error) {
	var out []Project
	_, err := c.getJSON(ctx, "/projects", nil, &out)
	return out, err
}

func (c *Client) GetProject(ctx context.Context, id int) (*Project, error) {
	var p Project
	if _, err := c.getJSON(ctx, fmt.Sprintf("/projects/%d", id), nil, &p); err != nil {
		return nil, err
	}
	return &p, nil
}

func (c *Client) CreateProject(ctx context.Context, name, description string) (*Project, error) {
	in := map[string]string{"name": name}
	if description != "" {
		in["description"] = description
	}
	var p Project
	if _, err := c.postJSON(ctx, "/projects", in, &p); err != nil {
		return nil, err
	}
	return &p, nil
}

// --- files ------------------------------------------------------------------

func (c *Client) ListFiles(ctx context.Context, id int, ref string) ([]FileEntry, error) {
	q := url.Values{}
	q.Set("ref", ref)
	var out FileListing
	if _, err := c.getJSON(ctx, fmt.Sprintf("/projects/%d/files", id), q, &out); err != nil {
		return nil, err
	}
	return out.Files, nil
}

// DownloadFile returns the exact bytes of a tracked file at a ref. repoPath is a
// repo path such as "l5x/<name>/source.L5X" or "files/<nested/path>".
func (c *Client) DownloadFile(ctx context.Context, id int, ref, repoPath string) ([]byte, error) {
	q := url.Values{}
	q.Set("ref", ref)
	q.Set("path", repoPath)
	data, _, err := c.getBytes(ctx, fmt.Sprintf("/projects/%d/files/raw", id), q)
	return data, err
}

// --- commits ----------------------------------------------------------------

// Log returns a branch's commit history (newest first) plus the branch total
// from the X-Total-Count header.
func (c *Client) Log(ctx context.Context, id int, branch string, limit, offset int) ([]Commit, int, error) {
	q := url.Values{}
	q.Set("branch", branch)
	q.Set("limit", strconv.Itoa(limit))
	q.Set("offset", strconv.Itoa(offset))
	var out []Commit
	resp, err := c.getJSON(ctx, fmt.Sprintf("/projects/%d/commits", id), q, &out)
	if err != nil {
		return nil, 0, err
	}
	return out, totalCount(resp.Header), nil
}

// Upload commits one or more files as a single commit (the multipart endpoint).
func (c *Client) Upload(ctx context.Context, id int, branch, title, description string, files []FilePart) (*CommitResult, error) {
	fields := map[string]string{"branch": branch, "title": title}
	if description != "" {
		fields["description"] = description
	}
	var res CommitResult
	if _, err := c.postMultipart(ctx, fmt.Sprintf("/projects/%d/commits", id), fields, files, &res); err != nil {
		return nil, err
	}
	return &res, nil
}

// --- branches ---------------------------------------------------------------

func (c *Client) ListBranches(ctx context.Context, id int) ([]Branch, error) {
	var out []Branch
	_, err := c.getJSON(ctx, fmt.Sprintf("/projects/%d/branches", id), nil, &out)
	return out, err
}

// CreateBranch creates a branch at startPoint and returns the refreshed branch
// list (the endpoint responds with all branches).
func (c *Client) CreateBranch(ctx context.Context, id int, name, startPoint string) ([]Branch, error) {
	in := map[string]string{"name": name}
	if startPoint != "" {
		in["start_point"] = startPoint
	}
	var out []Branch
	_, err := c.postJSON(ctx, fmt.Sprintf("/projects/%d/branches", id), in, &out)
	return out, err
}

func (c *Client) DeleteBranch(ctx context.Context, id int, name string) error {
	return c.delete(ctx, fmt.Sprintf("/projects/%d/branches/%s", id, name))
}

// --- diff -------------------------------------------------------------------

func (c *Client) DiffManifest(ctx context.Context, id int, base, head string) (*DiffManifest, error) {
	q := url.Values{}
	q.Set("base", base)
	q.Set("head", head)
	var out DiffManifest
	if _, err := c.getJSON(ctx, fmt.Sprintf("/projects/%d/diff", id), q, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) TextDiff(ctx context.Context, id int, base, head, path string) (*TextDiff, error) {
	q := url.Values{}
	q.Set("base", base)
	q.Set("head", head)
	q.Set("path", path)
	var out TextDiff
	if _, err := c.getJSON(ctx, fmt.Sprintf("/projects/%d/diff/text", id), q, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// ChangesetRaw / LadderRaw / CompareRaw return the diff payloads as opaque JSON
// (the CLI pretty-prints or passes them through to --json rather than modeling
// the full ChangeSet/LadderDocument trees).
func (c *Client) ChangesetRaw(ctx context.Context, id int, base, head, path string) (RawJSON, error) {
	return c.diffRaw(ctx, id, "changeset", base, head, path)
}

func (c *Client) LadderRaw(ctx context.Context, id int, base, head, path string) (RawJSON, error) {
	return c.diffRaw(ctx, id, "ladder", base, head, path)
}

func (c *Client) CompareRaw(ctx context.Context, id int, base, head string) (RawJSON, error) {
	q := url.Values{}
	q.Set("base", base)
	q.Set("head", head)
	var out RawJSON
	if _, err := c.getJSON(ctx, fmt.Sprintf("/projects/%d/compare", id), q, &out); err != nil {
		return nil, err
	}
	return out, nil
}

func (c *Client) diffRaw(ctx context.Context, id int, kind, base, head, path string) (RawJSON, error) {
	q := url.Values{}
	q.Set("base", base)
	q.Set("head", head)
	q.Set("path", path)
	var out RawJSON
	if _, err := c.getJSON(ctx, fmt.Sprintf("/projects/%d/diff/%s", id, kind), q, &out); err != nil {
		return nil, err
	}
	return out, nil
}

// --- pull requests ----------------------------------------------------------

// PullCreate is the body for opening a PR.
type PullCreate struct {
	Title        string `json:"title"`
	Description  string `json:"description,omitempty"`
	SourceBranch string `json:"source_branch"`
	TargetBranch string `json:"target_branch"`
}

func (c *Client) ListPulls(ctx context.Context, id int, statusFilter string, limit, offset int) ([]Pull, int, error) {
	q := url.Values{}
	if statusFilter != "" {
		q.Set("status_filter", statusFilter)
	}
	q.Set("limit", strconv.Itoa(limit))
	q.Set("offset", strconv.Itoa(offset))
	var out []Pull
	resp, err := c.getJSON(ctx, fmt.Sprintf("/projects/%d/pulls", id), q, &out)
	if err != nil {
		return nil, 0, err
	}
	return out, totalCount(resp.Header), nil
}

func (c *Client) GetPull(ctx context.Context, id, number int) (*Pull, error) {
	var p Pull
	if _, err := c.getJSON(ctx, fmt.Sprintf("/projects/%d/pulls/%d", id, number), nil, &p); err != nil {
		return nil, err
	}
	return &p, nil
}

func (c *Client) CreatePull(ctx context.Context, id int, in PullCreate) (*Pull, error) {
	var p Pull
	if _, err := c.postJSON(ctx, fmt.Sprintf("/projects/%d/pulls", id), in, &p); err != nil {
		return nil, err
	}
	return &p, nil
}

func (c *Client) PullDiffManifest(ctx context.Context, id, number int) (*DiffManifest, error) {
	var out DiffManifest
	if _, err := c.getJSON(ctx, fmt.Sprintf("/projects/%d/pulls/%d/diff", id, number), nil, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) PullMergeability(ctx context.Context, id, number int) (*Mergeability, error) {
	var m Mergeability
	if _, err := c.getJSON(ctx, fmt.Sprintf("/projects/%d/pulls/%d/mergeability", id, number), nil, &m); err != nil {
		return nil, err
	}
	return &m, nil
}

func (c *Client) MergePull(ctx context.Context, id, number int) (*MergeResult, error) {
	var r MergeResult
	if _, err := c.postJSON(ctx, fmt.Sprintf("/projects/%d/pulls/%d/merge", id, number), nil, &r); err != nil {
		return nil, err
	}
	return &r, nil
}

func (c *Client) ApprovePull(ctx context.Context, id, number int) (*Pull, error) {
	return c.reviewPull(ctx, id, number, "approve")
}

func (c *Client) RequestChangesPull(ctx context.Context, id, number int) (*Pull, error) {
	return c.reviewPull(ctx, id, number, "request-changes")
}

func (c *Client) reviewPull(ctx context.Context, id, number int, verb string) (*Pull, error) {
	var p Pull
	if _, err := c.postJSON(ctx, fmt.Sprintf("/projects/%d/pulls/%d/%s", id, number, verb), nil, &p); err != nil {
		return nil, err
	}
	return &p, nil
}

// AddComment posts a PR-level comment (parentID nil) or a reply.
func (c *Client) AddComment(ctx context.Context, id, number int, body string, parentID *int) (*Comment, error) {
	in := map[string]any{"body": body}
	if parentID != nil {
		in["parent_id"] = *parentID
	}
	var cm Comment
	if _, err := c.postJSON(ctx, fmt.Sprintf("/projects/%d/pulls/%d/comments", id, number), in, &cm); err != nil {
		return nil, err
	}
	return &cm, nil
}

// --- tags / releases --------------------------------------------------------

func (c *Client) ListTags(ctx context.Context, id, limit, offset int) ([]Tag, int, error) {
	q := url.Values{}
	q.Set("limit", strconv.Itoa(limit))
	q.Set("offset", strconv.Itoa(offset))
	var out []Tag
	resp, err := c.getJSON(ctx, fmt.Sprintf("/projects/%d/tags", id), q, &out)
	if err != nil {
		return nil, 0, err
	}
	return out, totalCount(resp.Header), nil
}

func (c *Client) CreateTag(ctx context.Context, id int, name, ref, message string) (*Tag, error) {
	in := map[string]string{"name": name}
	if ref != "" {
		in["ref"] = ref
	}
	if message != "" {
		in["message"] = message
	}
	var t Tag
	if _, err := c.postJSON(ctx, fmt.Sprintf("/projects/%d/tags", id), in, &t); err != nil {
		return nil, err
	}
	return &t, nil
}
