package client

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
)

// PollState is the result of one device-token poll.
type PollState int

const (
	PollPending  PollState = iota // keep polling at the current interval
	PollSlowDown                  // keep polling, but lengthen the interval
	PollDone                      // a token was issued
)

// RequestDeviceCode starts the OAuth 2.0 Device Authorization Grant (RFC 8628):
// POST /auth/device/code returns the device_code the CLI polls with and the
// user_code + verification URL the user approves in the browser.
func (c *Client) RequestDeviceCode(ctx context.Context) (*DeviceCodeResponse, error) {
	var out DeviceCodeResponse
	if _, err := c.postJSON(ctx, "/auth/device/code", map[string]any{}, &out); err != nil {
		return nil, err
	}
	if out.DeviceCode == "" {
		return nil, fmt.Errorf("device-code response missing device_code")
	}
	return &out, nil
}

// PollDeviceTokenOnce polls POST /auth/device/token once. On approval it returns
// the bearer token and PollDone. While the user hasn't approved yet it returns
// PollPending (or PollSlowDown). A terminal condition (expired/denied) returns a
// non-nil error. It tolerates both the RFC-8628 {"error": ...} body and
// FastAPI's {"detail": ...} so it works whichever way the backend implements it.
func (c *Client) PollDeviceTokenOnce(ctx context.Context, deviceCode string) (string, PollState, error) {
	body := `{"device_code":` + strconv.Quote(deviceCode) + `}`
	resp, err := c.request(ctx, http.MethodPost, "/auth/device/token", nil, "application/json", strings.NewReader(body))
	if err != nil {
		return "", PollPending, err
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))

	if resp.StatusCode >= 200 && resp.StatusCode < 300 {
		var tok tokenOut
		if err := json.Unmarshal(raw, &tok); err != nil {
			return "", PollPending, fmt.Errorf("decoding device token: %w", err)
		}
		if tok.AccessToken == "" {
			return "", PollPending, fmt.Errorf("device token response missing access_token")
		}
		return tok.AccessToken, PollDone, nil
	}

	switch deviceErrorCode(raw) {
	case "authorization_pending":
		return "", PollPending, nil
	case "slow_down":
		return "", PollSlowDown, nil
	default:
		return "", PollPending, &APIError{
			Status:  resp.StatusCode,
			Code:    codeForStatus(resp.StatusCode),
			Message: deviceErrorMessage(raw, resp.StatusCode),
		}
	}
}

// deviceErr captures both the RFC-8628 and FastAPI error shapes.
type deviceErr struct {
	Error  string `json:"error"`
	Detail string `json:"detail"`
}

func deviceErrorCode(body []byte) string {
	var d deviceErr
	_ = json.Unmarshal(body, &d)
	s := strings.ToLower(strings.TrimSpace(d.Error))
	if s == "" {
		s = strings.ToLower(strings.TrimSpace(d.Detail))
	}
	switch {
	case strings.Contains(s, "authorization_pending"), strings.Contains(s, "pending"):
		return "authorization_pending"
	case strings.Contains(s, "slow_down"), strings.Contains(s, "slow down"):
		return "slow_down"
	default:
		return s
	}
}

func deviceErrorMessage(body []byte, status int) string {
	var d deviceErr
	_ = json.Unmarshal(body, &d)
	if strings.TrimSpace(d.Detail) != "" {
		return d.Detail
	}
	if strings.TrimSpace(d.Error) != "" {
		return d.Error
	}
	return fmt.Sprintf("device authorization failed (status %d)", status)
}
