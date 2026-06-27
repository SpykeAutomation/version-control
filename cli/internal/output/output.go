// Package output centralizes human vs --json rendering. Data goes to stdout;
// progress/logs go to stderr in both modes, so a --json stdout is always a
// single clean value — the contract a future GUI parses.
package output

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
)

// Stable process exit codes — part of the GUI contract.
const (
	ExitOK       = 0
	ExitError    = 1
	ExitUsage    = 2
	ExitAuth     = 3
	ExitConflict = 4
	ExitNotFound = 5
	ExitQuota    = 6
	ExitTooLarge = 7
)

// Printer renders command output in the selected mode.
type Printer struct {
	JSON bool
	Out  io.Writer // stdout (data)
	Err  io.Writer // stderr (progress / errors)
}

// EmitJSON writes v as indented JSON to stdout (call only in JSON mode).
func (p *Printer) EmitJSON(v any) error {
	enc := json.NewEncoder(p.Out)
	enc.SetIndent("", "  ")
	return enc.Encode(v)
}

// EmitRawJSON writes pre-encoded JSON (e.g. a server ChangeSet) to stdout,
// indented. Used for structured payloads the CLI passes through rather than
// modeling — it prints in both human and JSON modes.
func (p *Printer) EmitRawJSON(raw []byte) error {
	var buf bytes.Buffer
	if err := json.Indent(&buf, raw, "", "  "); err != nil {
		_, werr := p.Out.Write(raw)
		return werr
	}
	buf.WriteByte('\n')
	_, err := p.Out.Write(buf.Bytes())
	return err
}

// Printf writes human output to stdout; a no-op in JSON mode.
func (p *Printer) Printf(format string, a ...any) {
	if p.JSON {
		return
	}
	fmt.Fprintf(p.Out, format, a...)
}

// Logf writes a progress/status line to stderr (shown in both modes).
func (p *Printer) Logf(format string, a ...any) {
	fmt.Fprintf(p.Err, format, a...)
}

// EmitError renders an error: a JSON envelope to stdout in JSON mode, otherwise
// a human line to stderr.
func (p *Printer) EmitError(code string, status int, message string) {
	if p.JSON {
		inner := map[string]any{"code": code, "message": message}
		if status > 0 {
			inner["status"] = status
		}
		_ = p.EmitJSON(map[string]any{"error": inner})
		return
	}
	fmt.Fprintf(p.Err, "error: %s\n", message)
}
