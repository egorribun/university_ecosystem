# ADR-048: Dev-only React Compiler schema compatibility boundary

## Status and date

Accepted by the repository owner on 2026-10-24. The staged compatibility
implementation is included; hosted compatibility and final-source validation
remain pending. Approval is not a passing audit.

## Context

Application schemas remain exclusively Valibot. The installed
`eslint-plugin-react-compiler@19.1.0-rc.2` depends on Zod 3, for which the
registry has no known patched compatible release for GHSA-mrhx-c7xc-m3w5.
The monolithic rule cannot be replaced with a weaker recommended hooks
configuration: wrapped and nested functions, unused opt-out directives,
severity filtering and suppression behavior must be preserved.

The read-only hosted artifact probe identified four external Zod imports in
the exact rc.2 bundle and recorded its npm integrity and source revision.
Registry provenance is not a reproduced-build proof. The separately installed
Babel compiler contains embedded pre-fix Zod code; removing vulnerable graph
nodes alone does not establish that the embedded code is fixed or exploitable.

## Decision

1. Permit one private, development-only compatibility boundary at
   `frontend/scripts/react-compiler-zod-compat/`, only for the exact rc.2
   ESLint consumer. It may use the mature, integrity-verified Zod 4.6.7 engine.
   No other direct Zod use is authorized.
2. Keep the original published ESLint plugin artifact byte-for-byte. Scope
   any dependency override to that exact consumer; use an honestly named
   local compatibility package, not a package falsely claiming to be Zod 3.
   If an internal engine alias is needed to avoid a recursive override, it
   must still identify the real `npm:zod@4.6.7` package in the lockfile.
3. Do not import `zod/v3`, retain a vulnerable engine for differential tests,
   add package lifecycle patching, or rewrite/evaluate the compiler bundle.
   Any required formatter change must be explicit and compatibility-tested.
4. Capture golden diagnostics from the currently installed rc.2 before
   changing its graph. Require tests-first RED/GREEN evidence for the facade,
   schema semantics, error handling, wrapped/nested functions, rule severity,
   suppression, suggestions and both unused opt-out directives.
5. Keep all application, browser, SSR and production-runtime validation on
   Valibot. Verify fresh development and production installs, actual consumer
   resolution, local-package realpaths and Docker transfer of the actual npm layout.
   The adapter and compiler must not enter the deployed runtime or client
   bundle.
6. Preserve every required gate, warning threshold, scanner finding and
   advisory disposition. Neither this exception nor a green npm graph
   authorizes dismissing the embedded Babel dependency risk.

## Narrow API and verification boundary

The source-linked consumer uses these factories: `array`, `boolean`, `enum`,
`function`, `lazy`, `literal`, `map`, `nativeEnum`, `nullable`, `number`,
`object`, `record`, `string`, `tuple` and `union`. This is not a general
Zod 3 replacement. Two known compatibility points are the legacy
`function().args(...)` builder and parsing/cloning of map defaults.

The first checkpoint used an importable null facade and failing assertions.
Hosted job 120802074003 captured 37 legacy fixtures and passed all five schema
controls; the eight intended facade assertions failed. The installed compiler
bundle hash matched the earlier integrity-verified npm artifact.

The next stage adds only the private dev package and its patched engine using
an npm-generated lock; the actual legacy-consumer override remains absent.
The full reviewed capture is retained as `legacy-baseline.json`. A test-owned
temporary module tree checks the unchanged compiler artifact with native Node
dependency resolution against the facade and the existing formatter 4.0.2.
It compares every diagnostic, suppression and suggestion, while separately
reporting wording changes for the two malformed configurations that must
still fail with the same InvalidConfig reason. This is not blanket permission
to change compiler messages, severity, defaults or suppression semantics.

Before the final consumer override, test the installed plugin against reviewed golden
records and the patched engine's early size-bound rejection. Resolve any
behavioral difference explicitly; do not silently normalize away diagnostics
or treat more configuration exceptions as an automatic improvement.

## Ownership and sunset

Owner: `@egorribun`. Review by 2027-01-10, or earlier when an official compatible
patched artifact becomes available. Any expansion beyond this exact tooling
consumer or any production use requires a new owner decision. Remove the
boundary when a validated official replacement preserves the existing gate.

## Evidence

- [GHSA-mrhx-c7xc-m3w5](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5)
- [Hosted artifact/provenance probe](https://github.com/egorribun/university_ecosystem/actions/runs/40065084160/job/120786781933):
  44 probe tests passed; rc.2 externalizes Zod, while the examined Babel
  compiler artifacts embed pre-fix code. This is not a fix verification.
- [Artifact probe source](../../scripts/ci/probe_react_compiler_artifacts.py)
- [Legacy baseline and assertion RED](https://github.com/egorribun/university_ecosystem/actions/runs/40069691438/job/120802074003)
- [Frontend standards](../../frontend/AGENTS.md)
