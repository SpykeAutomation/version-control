// Package client is the Spyke API REST client — the network half of the
// spykecore engine. It mirrors the endpoints in backend/app/routers and the
// response shapes documented in backend/README.md. It deliberately knows
// nothing about the local workspace or the terminal: a CLI or a GUI can drive
// it the same way.
package client

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/spykeautomation/spyke/spykecore/config"
)

// Client talks to one Spyke API base URL with an optional bearer token. Create
// one per command; it is safe for sequential use.
type Client struct {
	BaseURL string
	Token   string
	HTTP    *http.Client
}

// New returns a Client for baseURL (trailing slash trimmed) with an optional
// bearer token.
func New(baseURL, token string) *Client {
	return &Client{
		BaseURL: strings.TrimRight(baseURL, "/"),
		Token:   token,
		HTTP:    &http.Client{Timeout: 120 * time.Second},
	}
}

// FilePart is one file to send in a multipart upload. Name is the multipart
// field name (always "files" for commits); Filename is the logical upload name
// the server keys on (an L5X stem or a files/ relative path).
type FilePart struct {
	Name     string
	Filename string
	Content  io.Reader
}

// request builds and sends an HTTP request, returning the raw response (the
// caller must close Body). A non-2xx status is NOT treated as an error here —
// some endpoints (e.g. merge) return 200 with a conflict body — so callers
// decide. Use the expect* helpers for the common "2xx-or-APIError" case.
func (c *Client) request(ctx context.Context, method, path string, query url.Values, contentType string, body io.Reader) (*http.Response, error) {
	u := c.BaseURL + path
	if len(query) > 0 {
		u += "?" + query.Encode()
	}
	req, err := http.NewRequestWithContext(ctx, method, u, body)
	if err != nil {
		return nil, err
	}
	if c.Token != "" {
		req.Header.Set("Authorization", "Bearer "+c.Token)
	}
	if contentType != "" {
		req.Header.Set("Content-Type", contentType)
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", config.UserAgent)
	return c.HTTP.Do(req)
}

// expectJSON sends a request, and on a 2xx decodes the JSON body into out (which
// may be nil to discard it). Any non-2xx becomes an *APIError. The returned
// response has a drained, closed body but still exposes headers (e.g.
// X-Total-Count) to the caller.
func (c *Client) expectJSON(ctx context.Context, method, path string, query url.Values, contentType string, body io.Reader, out any) (*http.Response, error) {
	resp, err := c.request(ctx, method, path, query, contentType, body)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return resp, parseError(resp)
	}
	if out != nil {
		if err := json.NewDecoder(resp.Body).Decode(out); err != nil {
			return resp, fmt.Errorf("decoding %s %s response: %w", method, path, err)
		}
	} else {
		_, _ = io.Copy(io.Discard, resp.Body)
	}
	return resp, nil
}

func (c *Client) getJSON(ctx context.Context, path string, query url.Values, out any) (*http.Response, error) {
	return c.expectJSON(ctx, http.MethodGet, path, query, "", nil, out)
}

func (c *Client) postJSON(ctx context.Context, path string, in, out any) (*http.Response, error) {
	var buf bytes.Buffer
	if in != nil {
		if err := json.NewEncoder(&buf).Encode(in); err != nil {
			return nil, err
		}
	}
	return c.expectJSON(ctx, http.MethodPost, path, nil, "application/json", &buf, out)
}

func (c *Client) patchJSON(ctx context.Context, path string, in, out any) (*http.Response, error) {
	var buf bytes.Buffer
	if in != nil {
		if err := json.NewEncoder(&buf).Encode(in); err != nil {
			return nil, err
		}
	}
	return c.expectJSON(ctx, http.MethodPatch, path, nil, "application/json", &buf, out)
}

func (c *Client) postForm(ctx context.Context, path string, form url.Values, out any) (*http.Response, error) {
	return c.expectJSON(ctx, http.MethodPost, path, nil,
		"application/x-www-form-urlencoded", strings.NewReader(form.Encode()), out)
}

func (c *Client) delete(ctx context.Context, path string) error {
	_, err := c.expectJSON(ctx, http.MethodDelete, path, nil, "", nil, nil)
	return err
}

// getBytes fetches a raw (possibly binary) body, e.g. a file download. It
// returns the body bytes and the response headers on a 2xx, else an *APIError.
func (c *Client) getBytes(ctx context.Context, path string, query url.Values) ([]byte, http.Header, error) {
	resp, err := c.request(ctx, http.MethodGet, path, query, "", nil)
	if err != nil {
		return nil, nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, resp.Header, parseError(resp)
	}
	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, resp.Header, err
	}
	return data, resp.Header, nil
}

// postMultipart uploads files plus form fields (the commit endpoint) and
// decodes a 2xx JSON body into out.
func (c *Client) postMultipart(ctx context.Context, path string, fields map[string]string, files []FilePart, out any) (*http.Response, error) {
	var buf bytes.Buffer
	mw := multipart.NewWriter(&buf)
	for k, v := range fields {
		if err := mw.WriteField(k, v); err != nil {
			return nil, err
		}
	}
	for _, f := range files {
		part, err := mw.CreateFormFile(f.Name, f.Filename)
		if err != nil {
			return nil, err
		}
		if _, err := io.Copy(part, f.Content); err != nil {
			return nil, err
		}
	}
	if err := mw.Close(); err != nil {
		return nil, err
	}
	return c.expectJSON(ctx, http.MethodPost, path, nil, mw.FormDataContentType(), &buf, out)
}

// parseError turns a non-2xx response into an *APIError, pulling the FastAPI
// {"detail": ...} message (a string, or the first item of a 422 detail list).
func parseError(resp *http.Response) error {
	body, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	msg := ""
	var envelope struct {
		Detail json.RawMessage `json:"detail"`
	}
	if json.Unmarshal(body, &envelope) == nil && len(envelope.Detail) > 0 {
		var s string
		if json.Unmarshal(envelope.Detail, &s) == nil {
			msg = s
		} else {
			// 422 validation: detail is a list of {loc, msg, type}.
			var items []struct {
				Msg string `json:"msg"`
			}
			if json.Unmarshal(envelope.Detail, &items) == nil && len(items) > 0 {
				msg = items[0].Msg
			} else {
				msg = strings.TrimSpace(string(envelope.Detail))
			}
		}
	}
	if msg == "" {
		msg = strings.TrimSpace(string(body))
	}
	return &APIError{Status: resp.StatusCode, Code: codeForStatus(resp.StatusCode), Message: msg}
}

// totalCount reads the X-Total-Count pagination header (0 if absent/invalid).
func totalCount(h http.Header) int {
	var n int
	_, _ = fmt.Sscanf(h.Get("X-Total-Count"), "%d", &n)
	return n
}
