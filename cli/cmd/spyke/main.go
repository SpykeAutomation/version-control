// Command spyke is a git-like CLI for the Spyke PLC version-control platform.
// It is a thin shell over the spykecore engine; see internal/cli.
package main

import "github.com/spykeautomation/spyke/internal/cli"

func main() {
	cli.Execute()
}
