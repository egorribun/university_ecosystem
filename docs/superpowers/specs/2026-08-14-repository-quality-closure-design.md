# Repository Quality Closure Design

**Date:** 2026-08-14

**Status:** approved for autonomous execution by the user request

**Scope:** every tracked file in `university_ecosystem`, all supported runtime stacks, CI, supply-chain controls, and durable documentation

## Outcome

The repository will have a reproducible, current-HEAD quality record that does not confuse a high percentage with complete evidence. Every handwritten production source file will be represented in the inventory, every coverage dimension supported by its toolchain will be enforced at 100%, changed production lines will remain at 100% patch coverage, and viable mutants will remain at 100%. Files that cannot meaningfully produce line coverage, such as declarative infrastructure and documentation, will have explicit schema, contract, security, link, or rendering gates instead of fabricated coverage numbers.

The work is complete only when the local evidence, the pushed branch SHA, and the corresponding remote checks agree. A passing test suite with a failed upload, stale artifact, skipped security scanner, or undocumented exclusion is not closure.

## Approaches considered

1. **Manifest-driven closure (selected).** Generate a complete tracked-file inventory, normalize current-HEAD evidence per stack, close real gaps test-first, and ratchet each supported metric only after it reaches 100%. This is slower than changing thresholds but produces auditable evidence and prevents denominator gaming.
2. **Immediate global 100% thresholds.** Raise every threshold first and react to failures. This gives fast visibility but blocks unrelated work, obscures unsupported metrics, and encourages broad exclusions or coverage-only tests.
3. **Exclude difficult entrypoints and declarative files.** Keep the current near-100% floors while expanding omit lists. This would make the number look complete without testing the project and is rejected.

## Work decomposition

The programme is split into independently verifiable plans so that each plan leaves the repository green:

1. main CI and supply-chain closure;
2. current-HEAD coverage measurement and generated gap ledger;
3. Python closure;
4. frontend closure;
5. Go and Rust closure;
6. infrastructure, workflow, script, and contract closure;
7. documentation and repository-hygiene closure;
8. deep security scan and final release verification.

Each implementation change follows red-green-refactor. Configuration-only changes receive contract tests that fail against the broken configuration before the configuration is changed.

## Main CI and supply-chain design

### Trusted Codecov upload

The main failure is deterministic: `codecov/codecov-action@v7` defines `files` as a comma-separated input, while the workflow supplies a YAML literal block. The action forwards the entire newline-delimited value as one `--file` argument, so all nine real reports become one nonexistent filename and the uploader reports zero files.

The fix is to retain the isolated OIDC-enabled main-only upload job, keep `disable_search: true` and `fail_ci_if_error: true`, and pass the nine staged reports as one comma-separated value. A workflow contract test will assert the exact ordered list, the absence of newlines, the main-only guard, and the least-privilege OIDC permissions.

### Go and SBOM vulnerability gate

The current gate treats every OSV result without CVSS as HIGH. Go advisories commonly omit CVSS, so the job duplicates module-level findings across workspace modules and cannot distinguish reachable code from an unused package. The failure shown in the screenshot contains two standard-library advisories fixed after Go 1.26.4 and an all-version `openpgp` advisory even though no `openpgp` package is present in any executable dependency graph.

The repository will move every Go manifest, CI pin, benchmark image, and builder image to Go 1.26.6. The reporting job will continue to publish the full OSV SARIF so module-only findings remain visible. The blocking Go gate will use the official symbol-aware `govulncheck` pinned to a reviewed version and will fail on every reachable vulnerability, regardless of severity. This is stricter for exploitable code and avoids classifying an unreachable dependency advisory by guessed severity. No vulnerability ID will be silently ignored.

Docker builder images remain digest-pinned. Because the 1.26.6 official Alpine image is based on Alpine 3.24, the three Go builders move from the unavailable 1.26.6-alpine3.22 tag to the explicit 1.26.6-alpine3.24 multi-architecture digest. The protobuf and benchmark builders use the official 1.26.6-bookworm digest.

## Coverage and evidence model

The canonical source inventory starts from `git ls-files`, classifies generated, vendored, test, production, infrastructure, documentation, and tooling files, and records why each file belongs to an evidence contour. Handwritten production code may not disappear from a denominator without a versioned, expiring, independently validated exception; the target exception and quarantine registers are empty.

Supported dimensions are enforced as follows:

- Python: lines and branches from coverage.py; statements/functions are marked unsupported rather than set to zero.
- TypeScript/React: statements, lines, branches, and functions from Vitest/V8, with browser-only entrypoints measured by the browser coverage contour.
- Go: statement coverage from native coverprofiles plus source/file attribution; branch/function fields remain unsupported unless a trustworthy native tool supplies them.
- Rust: lines, regions/branches, and functions from LLVM coverage for every crate and feature contour.
- Scripts: executable Python, JavaScript, and shell logic receives unit or contract tests and is included in the appropriate runtime evidence.
- YAML, Docker, Helm, Compose, Kubernetes, and documentation: actionlint, schema rendering, policy tests, container builds, link checks, and deterministic contract tests replace meaningless line-coverage claims.

The normalized manifest must contain the current commit SHA, report hashes, generation time, per-file measurements, Tier 0 membership, and explicit unsupported dimensions. Project, component, per-file Tier 0, and patch policies are evaluated independently; one stack cannot compensate for another.

## Whole-repository audit

Every tracked file is processed by an inventory pass and at least one applicable automated or manual review surface. Static analysis, type checking, dependency scans, secret detection, container/IaC scanning, API contracts, and deep security discovery are additive; no single scanner is treated as a whole-project proof.

Validated defects found outside the immediate CI failures are fixed within their subsystem using the same test-first rule. Generated artifacts are regenerated from their source. Third-party or vendored content is identified and checked for provenance rather than edited as authored code.

## Documentation hygiene

Documentation is classified as canonical reference, active decision/plan, historical audit, generated report, tool/skill asset, or obsolete handoff/prompt. Canonical history and accepted architecture decisions are preserved. Stale execution ledgers, superseded handoffs, duplicate active roadmaps, orphaned prompts, and byte-identical tool assets with no supported consumer are removed or consolidated only after reference and provenance checks.

The final documentation surface will expose one current quality policy, one current execution record, the ADR/audit index, and generated dashboards. Historical material that remains useful stays under an explicit archive and is excluded from active guidance searches.

## Verification and publication

Each plan ends with focused tests and then its full stack gate. Final verification includes all unit/integration/contract suites, supported E2E and browser checks, Go race and vulnerability analysis, Rust tests and coverage, Docker build/startup contracts, Compose/Helm/Kubernetes rendering, dependency audits, secret/SAST/IaC/container scans, mutation policy, normalized coverage validation, and documentation/link checks.

Durable changes are committed without co-author trailers and pushed to `egorribun`. The remote branch SHA must equal the verified local SHA. Main-only checks are considered proven only by a post-integration main run; until then they are reported as fixed locally and branch-verified, not as green on main.

## Failure handling

Source regressions, scanner/tool failures, artifact freshness failures, and external service authorization failures are tracked separately. Retries do not convert a failure into evidence. If an external system prevents final proof, the repository will contain a precise continuation record with the command, run URL, SHA, and stable failure signature, while the goal remains incomplete.
