set -euo pipefail
scope_dir="$(mktemp -d "${RUNNER_TEMP%/}/osv-go-stdlib.XXXXXXXX")"
cleanup() {
  rm -f -- "$scope_dir/manifests" "$scope_dir/go.mod" "$scope_dir/osv-scanner.toml" "$scope_dir/stdlib.json"
  rmdir -- "$scope_dir"
}
trap cleanup EXIT

git ls-files -z -- ':(glob)services/**/go.mod' > "$scope_dir/manifests"
toolchain="$(GOTOOLCHAIN=local go env GOVERSION)"
version="$(python3 -I -B scripts/quality/verify_osv_go_stdlib_inventory.py --preflight "$scope_dir/manifests" "$toolchain")"

printf 'module example.invalid/osv-stdlib\n\ngo %s\n' "$version" > "$scope_dir/go.mod"
printf 'ScanGoModVersion = true\n' > "$scope_dir/osv-scanner.toml"
"$OSV_SCANNER_BIN" scan source --no-call-analysis=go --all-packages --all-vulns \
  --format json --config "$scope_dir/osv-scanner.toml" \
  --lockfile "$scope_dir/go.mod" --output-file "$scope_dir/stdlib.json"

python3 -I -B scripts/quality/verify_osv_go_stdlib_inventory.py "$scope_dir/stdlib.json" "$scope_dir/go.mod" "$version"
