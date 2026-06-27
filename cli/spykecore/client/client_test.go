package client

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func bg() context.Context { return context.Background() }

func newTestServer(h http.HandlerFunc) (*Client, func()) {
	srv := httptest.NewServer(h)
	return New(srv.URL, "tok"), srv.Close
}

func TestLoginAndMe(t *testing.T) {
	c, done := newTestServer(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/auth/login":
			_ = r.ParseForm()
			if r.Form.Get("username") != "a@b.com" || r.Form.Get("password") != "pw" {
				t.Errorf("login form = %v", r.Form)
			}
			_ = json.NewEncoder(w).Encode(map[string]string{"access_token": "T", "token_type": "bearer"})
		case "/auth/me":
			if r.Header.Get("Authorization") != "Bearer tok" {
				t.Errorf("auth header = %q", r.Header.Get("Authorization"))
			}
			_ = json.NewEncoder(w).Encode(map[string]any{"id": 1, "email": "a@b.com", "first_name": "A", "last_name": "B"})
		default:
			t.Errorf("unexpected path %q", r.URL.Path)
		}
	})
	defer done()

	tok, err := c.Login(bg(), "a@b.com", "pw")
	if err != nil || tok != "T" {
		t.Fatalf("Login = %q, %v", tok, err)
	}
	u, err := c.Me(bg())
	if err != nil || u.Name() != "A B" {
		t.Fatalf("Me = %+v, %v", u, err)
	}
}

func TestErrorMapping(t *testing.T) {
	cases := []struct {
		status int
		code   string
	}{
		{401, CodeAuth}, {403, CodeForbidden}, {404, CodeNotFound}, {409, CodeConflict},
		{413, CodeTooLarge}, {429, CodeRateLimit}, {507, CodeQuota}, {400, CodeBadInput},
	}
	for _, tc := range cases {
		c, done := newTestServer(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(tc.status)
			_ = json.NewEncoder(w).Encode(map[string]string{"detail": "boom"})
		})
		_, err := c.GetProject(bg(), 1)
		done()
		apiErr, ok := AsAPIError(err)
		if !ok {
			t.Fatalf("status %d: not an APIError: %v", tc.status, err)
		}
		if apiErr.Status != tc.status || apiErr.Code != tc.code || apiErr.Message != "boom" {
			t.Errorf("status %d: got %+v", tc.status, apiErr)
		}
	}
}

func TestValidationDetailList(t *testing.T) {
	// FastAPI 422: detail is a list of {loc,msg,type}.
	c, done := newTestServer(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(422)
		_, _ = w.Write([]byte(`{"detail":[{"loc":["body","name"],"msg":"field required","type":"missing"}]}`))
	})
	defer done()
	_, err := c.GetProject(bg(), 1)
	apiErr, ok := AsAPIError(err)
	if !ok || apiErr.Message != "field required" {
		t.Errorf("422 detail-list parse: %+v (ok=%v)", apiErr, ok)
	}
}

func TestDevicePolling(t *testing.T) {
	calls := 0
	c, done := newTestServer(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/auth/device/code":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"device_code": "DC", "user_code": "WXYZ",
				"verification_uri_complete": "http://x/cli-auth?code=WXYZ",
				"interval":                  1, "expires_in": 600,
			})
		case "/auth/device/token":
			calls++
			if calls < 2 {
				w.WriteHeader(400)
				_ = json.NewEncoder(w).Encode(map[string]string{"error": "authorization_pending"})
				return
			}
			_ = json.NewEncoder(w).Encode(map[string]string{"access_token": "FINAL"})
		default:
			t.Errorf("unexpected path %q", r.URL.Path)
		}
	})
	defer done()

	dc, err := c.RequestDeviceCode(bg())
	if err != nil || dc.DeviceCode != "DC" || dc.UserCode != "WXYZ" {
		t.Fatalf("RequestDeviceCode = %+v, %v", dc, err)
	}
	if tok, state, err := c.PollDeviceTokenOnce(bg(), dc.DeviceCode); err != nil || state != PollPending || tok != "" {
		t.Fatalf("first poll = %q, %v, %v", tok, state, err)
	}
	if tok, state, err := c.PollDeviceTokenOnce(bg(), dc.DeviceCode); err != nil || state != PollDone || tok != "FINAL" {
		t.Fatalf("second poll = %q, %v, %v", tok, state, err)
	}
}

func TestUploadMultipart(t *testing.T) {
	c, done := newTestServer(func(w http.ResponseWriter, r *http.Request) {
		if err := r.ParseMultipartForm(1 << 20); err != nil {
			t.Fatal(err)
		}
		if r.FormValue("branch") != "main" || r.FormValue("title") != "T" {
			t.Errorf("fields: branch=%q title=%q", r.FormValue("branch"), r.FormValue("title"))
		}
		fhs := r.MultipartForm.File["files"]
		if len(fhs) != 1 || fhs[0].Filename != "Line1.L5X" {
			t.Errorf("file parts: %+v", fhs)
		}
		_ = json.NewEncoder(w).Encode(map[string]string{"sha": "abc", "branch": "main", "title": "T"})
	})
	defer done()

	res, err := c.Upload(bg(), 1, "main", "T", "", []FilePart{
		{Name: "files", Filename: "Line1.L5X", Content: strings.NewReader("data")},
	})
	if err != nil || res.SHA != "abc" {
		t.Fatalf("Upload = %+v, %v", res, err)
	}
}

func TestTotalCountHeader(t *testing.T) {
	c, done := newTestServer(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-Total-Count", "42")
		_ = json.NewEncoder(w).Encode([]map[string]any{{"sha": "a", "title": "x"}})
	})
	defer done()
	_, total, err := c.Log(bg(), 1, "main", 1, 0)
	if err != nil || total != 42 {
		t.Fatalf("Log total = %d, %v", total, err)
	}
}
