# Lane L4 evidence (HEAD 811747bc9, branch egorribun, uncommitted working tree)

Format: ID | status | files | exact test names | command + result | hosted job that must be green

## AUD-313 | code-fixed+locally-proven (host/identity gate hardened; hosted stand job still needed)

Original criterion: owned-stand gate relies on env variables; seed rewrites the admin password.

- Admin password: already fail-closed at HEAD. `find_or_create_admin` raises on mismatch and never rekeys.
  Existing tests: `tests/test_seed_admin_data.py::test_reseeding_existing_admin_rejects_a_different_password_without_rekeying`,
  `tests/test_seed_admin_data.py::test_reseeding_existing_admin_with_the_matching_password_keeps_the_hash`. Passing.
- Gate identity (fixed in this lane): `require_owned_live_stand_target` now also requires an owner-issued record
  at fixed container path `/run/live-stand/owned-stand.json` (`OWNED_STAND_RECORD_PATH`), a regular file, at most 4096 bytes,
  exact keys `{schema_version, project_name, database_host}`, `schema_version` strict int 1, `project_name` equal to the owned
  project, `database_host` equal to the parsed DB host (`postgres`). Env flags are only cross-checked, not trusted alone.
- live_stand side: `_write_seed_owned_stand_record` writes `.secrets/owned-stand-seed.json` (O_EXCL, O_NOFOLLOW, 0600, atomic
  replace); `_seed_locked` mounts it read-only into every seed run and removes it in `finally`.
- Limit: the record is not cryptographically signed; trust comes from the host-side mount at a fixed path that only
  live_stand's `docker compose run -v` controls. A signed record (owner key mounted into the seed container) would be stronger
  and needs an owner decision on mounting key material into the seed container.
- Files: `scripts/seed_target.py`, `scripts/live_stand.py` (new helper + `_seed_locked` only), `tests/test_seed_owned_stand_record.py` (new),
  `tests/test_seed_demo_data.py` (one success test now provides the record), `tests/test_seed_live_authorization.py` (autouse record fixture; stand fixture creates worktree).
- Exact test names (new): `test_env_flags_alone_are_refused_without_the_owner_record`, `test_matching_owner_record_accepts_the_owned_stand`,
  `test_record_must_match_project_host_and_schema_exactly[*]` (8 cases incl. bool schema_version, extra key, non-object),
  `test_malformed_json_record_is_refused`, `test_oversized_record_is_refused_before_it_is_parsed`,
  `test_directory_in_place_of_the_record_is_refused`, `test_symlinked_record_is_refused`,
  `test_database_host_still_must_be_the_compose_postgres_service`, `test_admin_smoke_target_does_not_read_the_owned_stand_record`,
  `test_seed_writes_record_for_each_run_and_removes_it_afterwards`, `test_seed_removes_record_even_when_a_seed_run_fails`.
- Command + result: `uv run pytest tests/test_seed_owned_stand_record.py tests/test_seed_demo_data.py tests/test_seed_live_authorization.py tests/test_seed_admin_data.py tests/test_aud418_313_seed_guards.py tests/test_owned_seed_identity.py -q -p no:cacheprovider`
  -> 135 passed (before the final lint-only edits; rerun with --cov on seed_target: 90%, uncovered are pre-existing admin-smoke/env-reader branches and one defensive re-read branch).
  Wider run after the change: `tests/test_seed_demo_data.py tests/test_seed_owned_stand_record.py tests/test_seed_live_authorization.py tests/test_seed_admin_data.py tests/test_seed_demo_full_repeatability.py tests/test_aud418_313_seed_guards.py tests/test_owned_seed_identity.py tests/test_live_stand_resource_guard.py tests/test_live_stand_demo_seed_cli.py` -> 186 passed.
  Before the fix the new behavioural tests fail (no record gate at HEAD).
- Lint: `ruff check` and `ruff format --check` pass on the touched Python files. `mypy` on `scripts/seed_target.py`: 0 errors. `scripts/` is outside the AGENTS mypy gate (`app/` only).
- Hosted job: a PostgreSQL/owned live stand job (`start-docker.ps1` / `live_stand.py seed`) must run the seed to prove the record mount works with Docker Desktop bind mounts. Not run here (no owned stand started).

## AUD-309 | code-fixed+locally-proven (Windows); POSIX lock path proven only on Linux CI

Original criterion: live_stand subprocess calls without timeout, infinite lock waits.

- Already at HEAD: every `subprocess.run/Popen` in `scripts/live_stand.py` has `timeout=` (AST scan, see `_unbounded_subprocess_lines`).
  `process.wait(timeout=...)` used for the streaming Playwright child. Lifecycle lock waits are bounded by
  `LIVE_LIFECYCLE_LOCK_TIMEOUT_SECONDS = 10_800` on both msvcrt and fcntl paths.
- Tests (existing, passing natively): `tests/test_live_stand_subprocess_timeouts.py::test_every_live_stand_subprocess_call_declares_a_timeout`,
  `::test_generic_live_stand_command_timeout_becomes_a_stand_error`, `::test_git_probe_timeout_becomes_a_stand_error`,
  `::test_playwright_timeout_becomes_a_stand_error`, `::test_windows_lifecycle_lock_wait_is_bounded` (native Windows, PASS).
  `::test_posix_lifecycle_lock_wait_is_bounded` SKIPPED on Windows (fcntl) -> "Linux CI only".
- Command + result: `uv run pytest tests/test_live_stand_subprocess_timeouts.py -q` -> passed; 1 skipped (POSIX lock path).
- Hosted job that must be green: Linux CI job running `tests/test_live_stand_subprocess_timeouts.py` (the POSIX lock test).

## AUD-332 | code-fixed+locally-proven (native Windows run here); hosted Windows job needed for CI

Original criterion: `when_supported` symlink tests create symlinks without a privilege check.

- At HEAD: `tests/symlink_support.py` probes real `symlink_to` (directory and file). Every `*_when_supported` symlink test is gated.
  `tests/test_symlink_privilege_probe_contract.py::test_every_when_supported_symlink_test_is_probe_gated` and
  `::test_census_detects_an_ungated_when_supported_symlink_test` enforce the gate.
- Native result here: symlink privilege available (`DIRECTORY_SYMLINKS_SUPPORTED=True`, `FILE_SYMLINKS_SUPPORTED=True`), so the
  `when_supported` tests execute rather than skip: `test_common_git_metadata_rejects_reparse_directory_when_supported`,
  `test_worktree_owner_rejects_reparse_common_key_when_supported` (in `tests/test_start_docker_live_owner_key_paths.py`) PASS.
- Command + result: `uv run pytest tests/test_start_docker_live_stand_state_root.py tests/test_symlink_privilege_probe_contract.py tests/test_start_docker_live_owner_key_paths.py tests/test_live_stand.py tests/test_live_stand_acl_bytes.py -q -p no:cacheprovider -rs` -> 3084 passed, 1 skipped (`tests/test_start_docker_live_stand_state_root.py:976`, POSIX permissions and PowerShell 7 requirement, Linux CI only).
- Hosted job that must be green: a Windows-hosted job (lane L5 workflow) that runs these files without developer-mode assumptions, and records skips.
  Note for L5: the probe-gated tests run here only because this machine can create symlinks; a runner without that privilege will skip them with an explicit reason.

## AUD-436 | code-fixed+locally-proven (native Windows); hosted Windows job needed

Original criterion: live_stand `whoami` resolved through PATH; Git Bash ships a GNU whoami.

- At HEAD: `scripts/live_stand.py::_windows_system32_executable` resolves `whoami.exe`/`icacls.exe` under `%SystemRoot%\System32`
  (absolute, resolved, is_file). `_windows_user_sid` and all `icacls` calls use it.
- Native test (existing, passing): `tests/test_start_docker_live_stand_state_root.py::test_live_stand_uses_system32_acl_tools_when_git_usr_bin_precedes_path`.
  It puts Git's `usr/bin` first on PATH, asserts `shutil.which("whoami.exe")` is the Git binary, and asserts the live_stand resolver returns the System32 binary, then
  creates a private state root and checks the real ACL (owner SID and only current-user and SYSTEM rules).
- Command + result: included in the 3084-passed run above (`-k system32_acl` alone: 1 passed).
- Hosted job that must be green: Windows-hosted CI job (lane L5) running `tests/test_start_docker_live_stand_state_root.py`.

## AUD-373 | code-fixed+locally-proven for flag-on render, gateway routing and production gate; NOT closed (needs SPIRE staging run)

Original criterion: internal backend HTTP without TLS carries tokens and identity (`gateway-deployment.yaml:86-87`).
Owner decision: internal mTLS via SPIFFE/SPIRE, production-on. Orchestrator decision (2026-11-04) applied:

1. Flag-on routing: `templates/_helpers.tpl` `university-ecosystem.publicRouteService` maps public `/static` and `/.well-known`
   from backend to gateway only when `internalHttpMTLS.enabled=true`. Used by `ingress.yaml`, `gateway-api.yaml` (dormant; still blocked by
   validate-config) and the validation loop in `validate-config.yaml`. Flag-off: parsed render of all 53 staging resources is identical to the
   pre-change baseline (checked with sorted YAML dump). Flag-on: `/static` and `/.well-known` -> `university-ecosystem-gateway:8080`; other backend routes still fail.
2. Gateway edge: the catch-all NoRoute relays `/static` and `/.well-known` over the mTLS proxy transport (existing code). The gateway IP gate
   now exempts anonymous GET/HEAD under `/static/` (`services/gateway/middleware/ratelimit.go` `isPublicStaticRead`), mirroring the backend's
   `_is_static_like_path` exemption so NAT-shared client IPs are not throttled on images. `/.well-known/jwks.json` stays under the 100 rps / 200 burst IP gate.
3. Production-on: `validate-config.yaml` fails `global.environment=production` unless `internalHttpMTLS.enabled=true`. Staging stays opt-in.
   `.github/scripts/deploy-helm.sh` production branch appends `--set internalHttpMTLS.enabled=true` (only this setting edited there).
   Chart README and values.yaml comments document it.
4. Tests: `tests/test_aud373_internal_http_mtls_chart.py` (flag-off keeps /static, /.well-known on backend; flag-on routes them to gateway;
   flag-on refuses other plaintext backend routes; production without flag fails; production with flag renders with BACKEND_URL https;
   deploy-helm production branch sets the flag). `tests/test_helm_staging_contract.py` and `tests/test_helm_release_sha_contract.py`
   production renders now pass the flag; `tests/test_gateway_api_helm_contract.py` pins the `$pathService` effective-service form.
   `services/gateway/middleware/ratelimit_test.go`: `TestIsPublicStaticRead_OnlyAnonymousGetAndHeadUnderStatic`,
   `TestNewFallbackRateLimiter_ExemptsPublicStaticReadsButNotOtherRoutes`. `services/gateway/cmd/gateway/main_router_paths_test.go`:
   `TestSetupRouterRelaysPublicStaticAndWellKnownToBackend` (real router relays both paths to a backend origin).
5. Results: helm/network/ci_helm/gateway_api/aud373/spire/temporal/mfa_helm/workflow contract set: 906 passed, 2 failed (production MFA renders missing the flag and SPIFFE IDs), both fixed and rerun: test_mfa_helm_contract.py 18 passed; `helm lint . --strict` in the CI
   development mode and in flag-on production mode: 0 failed; `go vet ./...` clean; `gofmt -l` clean; `go test ./...` in services/gateway: all 7 packages ok.

Still required before closing (do NOT mark closed on render/unit proof):
- SPIRE staging run: SVID issuance and rotation for backend, gateway, ws-hub and file-processor; mTLS handshake on each hop (gateway->backend,
  ws-hub->backend JWKS, file-processor->backend JWKS); probe behaviour via `python -m app.server.internal_mtls probe`; a rejected non-listed client.
- Hosted: `tests/test_spiffe_worker.py` on Linux CI (gunicorn needs fcntl). Not runnable on Windows.
- Gateway `-race` on Linux CI.
- The `gatewayApi` route template remains blocked by validate-config; its flag-on backendRefs change is render-tested only in isolation.

Not runnable here: `tests/test_spiffe_worker.py` (fcntl), staging SPIRE cluster.

## AUD-322 | needs-hosted-CI (partial; not closed here)

Original criterion: event and chaos integration tests silently skip.

- `tests/integration/test_full_stack_flow.py`: the events CRUD path fails rather than skips (`skip_without_db` is the only environment gate; CI has PostgreSQL).
  No code change this lane.
- Chaos: `tests/chaos/test_resilience.py` (gated by `CHAOS_TESTS=1`), `tests/chaos/test_minio_chaos.py` and `tests/chaos/test_network_failures.py`
  (ToxiProxy, MinIO endpoint configuration). These are environmental gates, so an active run needs a chaos job with those services.
- Native contract tests passed: `tests/test_chaos_no_silent_skip_contract.py`, `tests/test_chaos_dry_run_gate.py`, `tests/test_chaos_loadtest_security.py` -> 29 passed.
- Hosted job that must be green: the nightly/chaos job with `CHAOS_TESTS=1` and ToxiProxy/MinIO up, with an execution receipt that the chaos-user login and no-chat cases ran (not skipped).

## AUD-506 | already-done for the original criterion at HEAD (hosted compose proof still needed)

Original criterion: Temporal JWKS over HTTP and a noop authorizer that accepts forged tokens.

- HEAD: `services/temporal/config.yaml` uses `${TEMPORAL_JWKS_URL}` (https, Caddy internal TLS) and `authorizer: "default"` (`claimMapper: "default"`). `dcRedirectionPolicy: noop` at line 163 is unrelated.
- Native test: `uv run pytest tests/test_temporal_jwks_https_contract.py` -> passed (included in the 61-passed run above).
- Reconciliation note says "service-token producer still lacks required permissions"; that is outside the original criterion and was not coded here.
- Hosted job that must be green: the Temporal compose stack job (Caddy JWKS TLS handshake and a default-authorizer request).

## Other owned tests not run here

- `tests/test_owned_nats_outage_cli.py`, `tests/test_helm*.py`, `tests/test_network*.py`: not touched by this lane; not re-run.
- Gateway `-race` not run (cgo not set up here); `go vet` not run.

## Workflow changes needed (lane L5 owns .github/**; not edited here)

1. Windows-hosted job: run `tests/test_start_docker_live_stand_state_root.py`, `tests/test_start_docker_live_owner_key_paths.py`, `tests/test_symlink_privilege_probe_contract.py`, `tests/test_live_stand_subprocess_timeouts.py`, `tests/test_seed_owned_stand_record.py` natively (AUD-332, AUD-436, AUD-309 Windows lock, AUD-313).
2. Linux job: run `tests/test_live_stand_subprocess_timeouts.py::test_posix_lifecycle_lock_wait_is_bounded` and `tests/test_spiffe_worker.py` (fcntl/gunicorn).
3. Chaos job: `CHAOS_TESTS=1` with ToxiProxy and MinIO endpoints; emit an execution receipt (AUD-322).

## Files changed by lane L4

- scripts/seed_target.py
- scripts/live_stand.py (only the seed-record helper, constants, and `_seed_locked`; `git diff` now shows just these two hunks, 67+/36-, no other lane's uncommitted hunks)
- tests/test_seed_owned_stand_record.py (new)
- tests/test_seed_demo_data.py
- tests/test_seed_live_authorization.py
- tests/test_spire_registration_plan.py (explicit short pytest ids for one parametrized case; the oversized id exceeded the Windows environment limit)
- charts/university-ecosystem/templates/_helpers.tpl, ingress.yaml, gateway-api.yaml, validate-config.yaml, values.yaml (comment), README.md (mTLS paragraph)
- .github/scripts/deploy-helm.sh (production branch only)
- services/gateway/middleware/ratelimit.go, ratelimit_test.go
- services/gateway/cmd/gateway/main_router_paths_test.go
- tests/test_aud373_internal_http_mtls_chart.py, tests/test_helm_staging_contract.py, tests/test_helm_release_sha_contract.py, tests/test_gateway_api_helm_contract.py
