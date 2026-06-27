package cli

import "fmt"

// usageError marks a user/argument mistake so renderError can return the usage
// exit code (2) rather than the generic error code.
type usageError struct{ msg string }

func (u *usageError) Error() string { return u.msg }

func usageErr(format string, a ...any) error {
	return &usageError{msg: fmt.Sprintf(format, a...)}
}

// short truncates a commit SHA to its 7-character prefix.
func short(sha string) string {
	if len(sha) > 7 {
		return sha[:7]
	}
	return sha
}
