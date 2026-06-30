package client

import (
	"context"
	"net/url"
)

// Login exchanges an email + password for a bearer token via the existing
// form-encoded /auth/login endpoint. This is the headless path (`--password`
// and CI); the interactive default is the device flow in device.go.
func (c *Client) Login(ctx context.Context, email, password string) (string, error) {
	form := url.Values{}
	form.Set("username", email) // OAuth2 form: "username" carries the email
	form.Set("password", password)
	var out tokenOut
	if _, err := c.postForm(ctx, "/auth/login", form, &out); err != nil {
		return "", err
	}
	return out.AccessToken, nil
}

// Me returns the authenticated user (GET /auth/me).
func (c *Client) Me(ctx context.Context) (*User, error) {
	var u User
	if _, err := c.getJSON(ctx, "/auth/me", nil, &u); err != nil {
		return nil, err
	}
	return &u, nil
}
