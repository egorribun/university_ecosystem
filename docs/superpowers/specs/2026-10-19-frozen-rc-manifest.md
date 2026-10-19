# Reviewed frozen-RC selection

Date: 2026-10-19 (Europe/Istanbul). Scope: owner-approved replacement of the manual frozen_rc_sha dispatch input with a reviewed tracked manifest. Source-only implementation on egorribun; no RC selection, default-branch bootstrap, merge or deployment is authorized.

## Outcome and security boundary

Remove the nonempty workflow_dispatch inputs that trigger Checkov CKV_GHA_7 without suppressing the rule or weakening release safety. Manual full smoke must still run on exactly the reviewed frozen source SHA, never silently fall back to the workflow SHA, a branch tip or a tag.

Keep the existing main-only manual validation and full-smoke conditions. The validation job first rejects non-main invocation before checkout. It checks out the trusted workflow commit github.sha with persisted credentials disabled, verifies HEAD equals that exact SHA, and reads only quality/frozen-rc.json from that checkout. No environment variable, dispatch input or alternate user-provided file can override the selected manifest.

## Manifest and bounded validator

The initial tracked manifest has exactly schema_version equal to integer 1 and source_sha equal to null. Null explicitly means unfrozen and must block manual full smoke. Later selection requires a reviewed source change to a lowercase 40-hex commit SHA; a boolean schema version, extra or missing field, duplicate JSON key, wrong root/type, whitespace-padded SHA or malformed value is invalid.

A standard-library CLI in scripts/quality/resolve_frozen_rc_manifest.py accepts --manifest for the fixed workflow path. Reject missing files, directories, symlinks and other nonregular files before opening; reject non-UTF-8, malformed or excessively nested JSON, read errors and inputs exceeding 4096 bytes. Read at most 4097 bytes rather than loading an unbounded document. The trusted immutable checkout is the filesystem boundary; this does not claim resistance to an adversary swapping filesystem objects concurrently. Keep a pure parse_manifest API without CLI side effects.

Success prints only the exact SHA and a newline with exit status zero. Every manifest validation/read failure returns status one, empty stdout, and the fixed diagnostic "ERROR: frozen RC manifest is invalid or not frozen". Do not expose raw input, paths, exceptions or tracebacks. Ordinary command-line usage errors remain argparse's own interface; the workflow always passes its fixed supported arguments.

## Exact checkout and lifecycle

The shell revalidates the parser's output before publishing source_sha through GITHUB_OUTPUT. The frozen-smoke job consumes only the successful validation job's output, retains the manual-event/main-ref guards and performs its exact-SHA checkout as its first step. Verify the checkout immediately before setup or dependency installation. Pass that verified SHA unchanged to live_stand.py up --ref.

Preserve full stack/full mode, disabled caches, existing owner-scoped state directory with run ID and attempt, and in-place execution. Up, E2E and stop must use the same owned state directory. Always stop a started owned stand; do not introduce teardown, global cleanup or changes to unrelated resources. Keep metadata-only outcome receipts and always-upload behavior, exact verified-SHA/run/attempt artifact naming, and 90-day retention. Never copy all environment variables or captured stdout/stderr into receipts.

PR Core and nightly behavior, concurrency ownership, permissions, pinned actions, required checks, baseline and security dispositions remain unchanged.

## Evidence and publication order

1. Publish contract tests and an additional focused check before production implementation. Observe hosted assertion failures for the missing validator/manifest and old dispatch contract, not merely formatter or collection failures.
2. The focused check runs in existing backend shard zero after locked dependency sync. It uses its own temporary coverage configuration/data and requires 100% validator line/branch coverage. It does not replace or alter full unit shards, their coverage artifacts, provenance, aggregate thresholds or required contexts.
3. Implement the smallest validator, initially unfrozen manifest and workflow source transition. Update current operational instructions without erasing historical audit evidence.
4. Require passing focused contracts and validator coverage, standard hosted full CI and Checkov on the implemented source. A passing source contract does not mean manual full smoke ran.
5. Keep actual RC selection and release acceptance pending until their authorized operational conditions are met.

## Default-branch activation limitation

GitHub manual/scheduled workflow activation and the existing main-only guard require the trusted workflow and manifest on the default branch. The release plan separately requires full smoke of the frozen candidate before ordinary merge. Branch-only source changes do not resolve that bootstrap/order dependency and do not grant permission to update main.

Do not substitute github.sha on main for the candidate, allow arbitrary branch dispatch, choose an RC automatically or claim a pre-merge full smoke from source tests. Record the remaining activation/selection decision explicitly when release reaches that stage.
