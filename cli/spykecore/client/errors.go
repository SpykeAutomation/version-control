package client

import (
	"errors"
	"fmt"
)

// APIError is a structured error decoded from a non-2xx Spyke API response.
// Its Code field doubles as the machine-readable error code in `--json` output.
type APIError struct {
	Status  int    // HTTP status code
	Code    string // short machine code (see the Code* constants)
	Message string // human-readable detail (from the body's {"detail": ...})
}

func (e *APIError) Error() string {
	if e.Message != "" {
		return e.Message
	}
	return fmt.Sprintf("request failed with status %d", e.Status)
}

// Machine-readable error codes. These appear in `--json` error envelopes and
// map to process exit codes in the CLI layer.
const (
	CodeAuth      = "auth"           // 401
	CodeForbidden = "forbidden"      // 403
	CodeNotFound  = "not_found"      // 404
	CodeConflict  = "conflict"       // 409
	CodeTooLarge  = "too_large"      // 413
	CodeRateLimit = "rate_limited"   // 429
	CodeQuota     = "quota_exceeded" // 507
	CodeBadInput  = "bad_input"      // 400 / 422
	CodeServer    = "server_error"   // 5xx
	CodeOther     = "error"          // anything else
)

func codeForStatus(status int) string {
	switch status {
	case 401:
		return CodeAuth
	case 403:
		return CodeForbidden
	case 404:
		return CodeNotFound
	case 409:
		return CodeConflict
	case 413:
		return CodeTooLarge
	case 429:
		return CodeRateLimit
	case 507:
		return CodeQuota
	case 400, 422:
		return CodeBadInput
	default:
		if status >= 500 {
			return CodeServer
		}
		return CodeOther
	}
}

// AsAPIError returns the *APIError in err's chain, if any.
func AsAPIError(err error) (*APIError, bool) {
	var apiErr *APIError
	if errors.As(err, &apiErr) {
		return apiErr, true
	}
	return nil, false
}

// IsUnauthorized reports whether err is an API 401 (expired/invalid token).
func IsUnauthorized(err error) bool {
	if apiErr, ok := AsAPIError(err); ok {
		return apiErr.Status == 401
	}
	return false
}
