# Audit closure handoff (2026-11-03, second pause)

Temporary work plan for the agent that continues AUDIT-2026-10 closure while the
owner is away. Delete this file, [2026-11-03-audit63-lanes.md](2026-11-03-audit63-lanes.md)
and [2026-11-03-audit-evidence/](2026-11-03-audit-evidence/) when the work is done.
It records no new audit acceptance: the accepted lower bound stays as stated in
[docs/audits/INDEX.md](../../audits/INDEX.md) until hosted evidence is reconciled.

## Start here

1. Read [AGENTS.md](../../../AGENTS.md) in full. Work only on branch `egorribun`
   (PR #1343 against `main`). `git fetch` first.
2. Read "State on 2026-11-04" below first: the WIP commit and steps 1-2 of
   this file are finished. Never amend or force-push.
3. Then continue the lanes in [2026-11-03-audit63-lanes.md](2026-11-03-audit63-lanes.md).
   Per-lane evidence notes are in [2026-11-03-audit-evidence/](2026-11-03-audit-evidence/)
   (`round5-*.md` are the newest).

## State on 2026-11-04

- A cloud agent finished the WIP lanes and both owner items (AUD-208 Squawk
  exception, now 5 rules, owner-confirmed 2026-11-04; AUD-482 go-jose and
  x/crypto) in `2d3ee026f..e2a322e34`. A full review found and fixed in
  `6c460ee3d..811747bc9`: the Alembic job seeded the schema before the
  empty-schema guard; npm audit (minimatch via eslint plugins, now a
  first-party adapter); dead Workbox generateSW tests; per-user rate-limit
  keying limited to access tokens with UUID subjects; a chaos dry-run that
  faked a healthy target; the plist license label rebind (ADR-047); chart
  egress that silently broke external MinIO/Elasticsearch.
- Round 5 (`a7f1a573b..a17b0944e`) code for 360, 392, 426, 447, 454, 313,
  309, 332/436 (Windows CI job), 373 (production requires internal mTLS;
  public /static and /.well-known via the gateway when it is on), 480, 483
  (Go x/crypto and x/net patched in every module, OSV gate on PRs), 245, 384,
  334, 428 (TypeScript census), 432 (partial). See `round5-*.md` for each ID's
  status and the hosted job that must prove it.
- Owner items: set repository variables `MINIO_EGRESS_CIDRS` and
  `ELASTICSEARCH_EGRESS_CIDRS` before any staging/production deploy with an
  external MinIO or Elasticsearch; production now needs SPIRE and internal
  mTLS. AUD-272 needs owner acceptance (the ledger enforces delivery-once; the
  old redundant `uq_notification_delivery_once` stays in the baseline under
  ADR-051). AUD-373 needs a SPIRE staging run. AUD-381 thresholds and the
  AUD-429 live realtime job are owner decisions.

## Done and pushed this session (89e1f90e7..WIP)

- Review of the 32 cloud-agent commits plus 2 Dependabot merges: no blocker.
- **Root cause of Owned Live Acceptance `stage=send http_status=500`:**
  `ChatRepository.create_message` never bound `app.current_user_id`. The
  backend runs as `ue_app` (NOBYPASSRLS), so `messages_participant_isolation`
  rejected the INSERT. Fixed in `dc70dfcb4`. The CI integration DB user is a
  superuser and bypasses RLS, which is why CI missed it. RLS tests now use
  `tests/fixtures/rls_runtime_role.py` (NOSUPERUSER NOBYPASSRLS, production
  grants). On `f76a99634` the NATS outage step passed.
- `1e4dd5f1c`: partition DDL and retention pruning run only through
  `python -m app.services.partition_manager` as `ue_migrator` (compose and the
  Helm migration job). The runtime refuses. Each `data_access_logs` leaf is
  revoked for `ue_app`.
- `3bb601ddf` and `0046560f2`: the phone redactor corrupted about 20% of UUIDs
  in logs. Only canonical hyphenated UUIDs are protected now.
- `ecba3740c` and `0046560f2`: a finite failure record for every propagated
  exception, via a context manager that never suppresses.
- `f76a99634`: SW replay keeps a row whose payload changed in flight.
- `92cc0b597` (L1), `484a16b0f` (L6), `de6e0d93b` (L3): audit lane work. See the
  evidence notes.

## Step 1: finish the WIP commit

Verify each part, fix it, and commit it separately:

- **L1:** removal of detect-secrets, disposition and Gitleaks identities whose
  files no longer exist, and the pinned counts (AGENTS.md, docs/README.md,
  STATUS.md, tests). The stop came while updating the Gitleaks count pins.
  Removing stale identities is an owner-approved tightening; adding any is not.
  A disposition-policy change is committed with
  `UE_DETECT_SECRETS_OWNER_AUTHORED_DISPOSITION_UPDATE=1`. In `docs/audits/**`,
  only those inventory count numbers may change.
- **L2 (AUD-164):** `app/core/ratelimit/middleware.py` keys every request by
  client IP, so all live-stand users share one 200/window bucket. The browser
  E2E then flakes on 429, and flaky counts as a failure.
  - Target: requests with a verified access token (same verification as
    `app/core/ratelimit/fastapi.py`) are keyed per user.
  - Anonymous requests and auth endpoints (login, register, reset) stay per-IP.
  - No limit increase and no stand exemption.
  - Tests: two users from one IP get separate buckets; a forged token falls
    back to the IP key; XFF from an untrusted peer is ignored.
  - Then the rest of L2: 392, 360, 450/272, 454, 426, 447.
- **L4:**
  - NetworkPolicy egress narrowing (AUD-189).
  - SPIRE RBAC (AUD-251).
  - Trusted-proxy defaults (AUD-167 deployment part): chart
    `gateway.config.trustedProxies` was `[]` and ws-hub was loopback only; the
    same in `docker-compose.full.yml` and `docker-compose.go.yml`. Trust exactly
    the proxy hop the templates prove. Compose tests pin the old loopback
    default, so update them.
  - Then 313, 373, 309/436/332, and record 169/188.
- **L5:**
  - Semgrep CI job or claim removal (380).
  - Chaos dry-run assertions (346).
  - Slack `if` (384).
  - Supply-chain scanners (480/483, `tests/test_aud_supply_chain_scanner_contracts.py`).
  - Wiring `tests/test_caddy_emitted_log_redaction_docker.py` (needs
    `RUN_DOCKER_PROOFS=1` and `CADDY_PROOF_IMAGE`) into a PR job, and the
    ci-check-catalog plus CI Success `needs` entries. The stop came here.
  - `.github/workflows/reusable-backend-tests.yml` has a reviewed-bytes model in
    `tests/test_verify_secrets_baseline.py`; avoid editing it.
- **L6 (AUD-432):** registration and full-SSR contracts as behaviour (the new
  `register-double-submit.decisions.mjs` and `ssr-document-render.spec.ts`).
  The stop came mid-splice in `ssr-hydration-i18n.contract.test.mjs`: check for
  duplicate helpers or imports. `npm run build` rewrites tracked WASM files;
  restore them with `git checkout` before committing. Then AUD-334 client side:
  `useChatWebSocket` healthy-heartbeat cap (expects at most 11 transports,
  observed 12).

## Step 2: owner-decided items not yet implemented

- **AUD-208 (owner, 2026-11-03):** an exact Squawk exception for
  `alembic/versions/202611020000_mvp_baseline.py` only. It disables
  `require-concurrent-index-creation`, `constraint-missing-not-valid` and
  `adding-foreign-key-constraint`; check the names against the CI-pinned
  Squawk 2.67.0.
  - The reason: the baseline applies only to an empty schema. A test proves the
    baseline refuses a non-empty schema.
  - A contract test fails if the exception widens to another file or rule.
  - Raw Squawk with only those three off must report 0.
  - `.squawk.toml` uses the key `exclude-rules`, which Squawk may ignore: verify
    the real key.
  - Add an ADR-051 addendum. Every other migration keeps the full rule set.
- **AUD-482 (owner, 2026-11-03):**
  - Add GHSA-4w3g-jfj2-cw2q and GHSA-vvm8-gf78-28g4 to the existing go-jose/v3
    exception, same scope (`services/caddy/go.mod` only, owner egorribun, expiry
    2027-01-10), everywhere GHSA-mgcc-cww5-fp2q appears, plus an ADR-047 note
    and binding tests.
  - Pin `golang.org/x/crypto` in `services/caddy` to the official pseudo-version
    that fixes GO-2026-5932 (`go mod verify`, `-mod=readonly` build, osv
    re-run).

## Rules that must hold

- No `--no-verify`, force-push, admin bypass or `Co-Authored-By` trailer. Do not
  merge PR #1343 before every required check is green on the exact SHA. Do not
  tag v1.0.0, publish to GHCR or deploy: those need the owner.
- Never weaken a gate, threshold, required check or coverage floor. No inline
  secret-allowlist suppressions, `type: ignore`, `nosemgrep`, skip or xfail.
  `# noqa: S603  # <reason>` on a fixed-argv subprocess call is accepted.
- Security inventories: 1:1 line rebinds (detect-secrets updates line numbers
  on commit) and removal of identities whose file is gone are allowed. A new
  identity needs the owner: generate test secrets at runtime or derive public
  ids from source lines.
- Audit documents (`docs/audits/**`) change only after hosted CI is green on an
  exact SHA, with named job receipts. Original criteria are never narrowed.
- Linux CI is authoritative. Owned PostgreSQL and Docker proofs run there.

## Owner decisions in force

- ADR-051: one Alembic baseline `202611020000`, with schema equivalence against
  the pre-squash commit `3ff5375fb`. It has exactly one approved replacement:
  `messages_participant_isolation` with the NULLIF form (2026-11-03). Nothing is
  deployed, so migration-history findings close by removal plus the equivalence
  receipt.
- go-jose/v3 exception and `howett.net/plist` license exception as recorded in
  ADR-047 (extend go-jose as in step 2).
- Password policy: minimum 12 and zxcvbn ≥ 2. Internal mTLS via SPIFFE/SPIRE
  behind a production-on flag. The application DB role is not a superuser.
  Policies only tighten.
- Pre-authorized: push verified rounds; rerun CI only for a proven
  infrastructure failure (for example a Rekor timeout in SLSA); merge green
  Dependabot PRs; an ordinary merge of #1343 once every required check is green.
- Hard date: 2026-11-13.

## Known follow-ups

- SpiceDB and Temporal still use the bootstrap superuser
  (`KNOWN_SUPERUSER_RUNTIME`).
- Daily retention: partition pruning now runs on every migration run only;
  there is no scheduled migrator job.
- `run_periodically` in `partition_manager` catches only some exception classes.
- Redaction: a digit-only phone glued to a UUID, or followed by a long digit
  run, is not redacted (pre-existing). Changing it alters all long numeric runs.
- SW replay: a payload rewritten after delivery is resent under the same
  Idempotency-Key. Production never rewrites queued rows.
- Test hygiene: `tests/test_full_backend_reusable_contract.py` has a test after
  `__main__`; tautologies in `tests/test_dependency_resolution_policy.py` and
  the tier-0 rglob check; a CWD-relative path in `tests/test_internal_http_mtls.py`;
  pgbouncer substring checks; setup-python literals duplicated in five tests.
- Frontend OpenTelemetry downgrade rationale (`eb470c8e4`) needs an ADR. Helm
  default values fail `helm lint` (pre-existing, fails closed).
