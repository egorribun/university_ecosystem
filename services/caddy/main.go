// Command caddy is the repository edge proxy: upstream Caddy with the
// caddy-ratelimit module compiled in. It replaces the xcaddy generator, which
// resolved the module graph again on every image build.
package main

import (
	_ "time/tzdata"

	caddycmd "github.com/caddyserver/caddy/v2/cmd"

	// Modules compiled into the edge binary. Keep this list in step with go.mod.
	_ "github.com/caddyserver/caddy/v2/modules/standard"
	_ "github.com/mholt/caddy-ratelimit"
)

func main() {
	caddycmd.Main()
}
