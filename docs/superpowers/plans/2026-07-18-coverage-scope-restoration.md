# Restoration of honest frontend coverage scope

## Objective

Make frontend coverage describe every executable production source file under
`frontend/src`, rather than a hand-selected subset.  Keep the quality contract
strict: do not lower thresholds, do not exclude pages or feature code merely to
make a percentage pass, and keep Node-native WASM checks in the CI test command.

## Evidence captured before the change

- `npm run test:ci` completed successfully on 2026-07-18: 11 Node/WASM tests and
  3,206 Vitest tests passed.
- Its report nevertheless showed 100% only for the narrow `coverage.include`
  allow-list in `frontend/vitest.config.ts`; the configuration excluded
  `src/pages/**/*` wholesale and omitted most of `src`.
- The quality normalizer defines the frontend source root as `frontend/src`, so
  the runner's allow-list and the repository quality contract disagree.

## Source-wide baseline (2026-07-18)

- The complete source-wide run executed all 3,206 Vitest tests successfully
  (`0` failures, `0` errors; 684.58 seconds).  The separate Node/WASM suite is
  also part of `test:ci` and had already passed 11 checks.
- With `src/**/*.{ts,tsx}` in the denominator, the measured result is 88.85%
  statements/lines (44,015 of 49,538), 82.61% functions (1,739 of 2,105), and
  82.25% branches (8,704 of 10,582).  It correctly fails the existing 99/98%
  contract floors.
- The largest completely unexecuted production modules are
  `pages/StoriesAdmin.tsx` (608 coverage items), `pages/NewsDetail.tsx` (350),
  `pages/EventDetail.tsx` (229 statement/branch items), followed by focused
  UI and page modules.  This prioritizes the first test batches; it does not
  justify an exclusion.

## Progress update (2026-07-19)

- The first focused batch added behavioural tests for the three detail/admin
  page orchestrators, App/Map/Messenger mounting, layout accessibility,
  article navigation, marker a11y cleanup, Spotify connection handling, and
  security-sensitive settings hooks (password, email, DND).
- The second complete run passed 3,253 Vitest tests with zero failures/errors
  in 708.36 seconds; the explicit Node/WASM suite passed all 11 checks.
- Measured source-wide coverage is now 91.81% statements/lines (45,484 of
  49,538), 82.26% functions (1,790 of 2,176), and 82.14% branches (8,997 of
  10,952).  This is an honest +2.96 percentage-point improvement in lines from
  the initial source-wide baseline.  The 99% statements/lines and 98%
  functions/branches floors remain intentionally unchanged and currently fail.

## Execution plan

1. Replace the allow-list with `src/**/*.{ts,tsx}` and retain only principled
   exclusions: declarations, generated API clients, test files, stories,
   bootstrap-only entries, and server/worker entry points that cannot run in the
   jsdom unit runtime.
2. Run the complete `npm run test:ci` suite to produce a source-wide baseline.
   Preserve the produced LCOV report as evidence; a failed strict threshold is a
   finding, not a reason to hide files or relax the policy.
3. Compare LCOV paths against the source inventory and classify every omitted
   file as either testable production code or a documented runtime-only entry.
4. Add focused tests in descending uncovered-risk order (security/auth,
   API/validation, state management, routes/pages, UI behavior, error paths).
   Every new test must have behavioral assertions, not import-only coverage.
5. Raise or enforce source-wide floors only after the measured value supports
   them.  The end state is source-wide metrics at the repository contract floors
   (99% statements/lines, 98% branches/functions) and 100% for tier-0 paths.
6. Re-run Node WASM tests, Vitest coverage, TypeScript, ESLint, Prettier, and the
   quality-manifest normalizer before declaring this work complete.

## Guardrails

- Do not restore `src/pages/**/*` or any broad production directory exclusion.
- Do not change the quality contract's numerical floors downward.
- Do not count test, story, declaration, generated-client, or build-output files
  as production coverage.
- Node `node:test` WASM suites remain explicit in `test:ci`; Vitest excludes them
  only because it is a different test runner.
