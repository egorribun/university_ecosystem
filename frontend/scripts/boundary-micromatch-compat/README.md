# Boundary micromatch compatibility adapter

This private, repository-owned package supplies only the three micromatch APIs
used by `eslint-plugin-boundaries@7.2.0` and its `@boundaries/elements@3.1.1`
dependency: `isMatch`, `capture`, and `makeRe`. It is not a general replacement
for micromatch and must not be used by application code or other tools.

The wrappers are adapted from [micromatch 4.0.8's official source](https://github.com/micromatch/micromatch/blob/4.0.8/index.js),
distributed in the [official npm package](https://registry.npmjs.org/micromatch/-/micromatch-4.0.8.tgz).
The original MIT license and copyright are retained in `LICENSE`. Changes are
limited to CommonJS exports, formatting, local variable names, and `const`.
The engine is pinned to **picomatch 2.3.2**, the same version previously resolved
inside micromatch 4.0.8. The frontend's separate picomatch 4.x consumers retain
their own engine. Review the private `picomatch/lib/utils` import when upgrading.

## Why this exists

Micromatch 4.0.8 loads `braces` even though these three methods use only picomatch.
[GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) reports
stack exhaustion in braces through 3.0.3 with no patched version as of 2026-10-03.
Removing the unused dependency eliminates that vulnerable package from the lint
toolchain without disabling the architecture rules. This is dependency removal,
not a claim that ordinary boundary linting exercised the vulnerable walkers.

The adapter has its own honest name and version. A frontend devDependency named
`micromatch` points to `file:./scripts/boundary-micromatch-compat`; a scoped
`eslint-plugin-boundaries@7.2.0` override references `$micromatch` for both
consumers. The direct boundary dependency is pinned to that reviewed version to
keep the scoped override valid. Preserve that pairing: a direct nested `file:` override can create
broken relative symlinks that a clean audit alone will not detect.

## API and compatibility limits

- `isMatch(string, patterns, options)` preserves picomatch's any-match array
  semantics, including negation. Arrays are not ordered inclusion/exclusion lists.
- `capture(glob, input, options)` preserves glob string coercion, Windows slash
  normalization, capture ordering, empty strings for absent groups, and
  `undefined` when there is no match.
- `makeRe(...args)` forwards all arguments to the same picomatch engine.
- No callable default export or other micromatch methods are supplied. Calling
  an unsupported API throws `TypeError`; there is no silent fallback. In
  particular, `braces`, `braceExpand`, and parser/expansion APIs are unavailable.

Picomatch still handles brace alternatives and ranges in its regular-expression
compiler. This adapter does not add an expansion API, parser, or security claim
covering all possible expensive regular expressions.

## Maintenance and removal

This package is now repository-maintained code. Before upgrading either boundary
consumer, recheck its actual micromatch calls and options, including transitive
consumers. Do not broaden the override to other packages. Investigate any new API
use instead of adding an unreviewed compatibility shim. Track security updates
for picomatch and reassess its exact version with compatibility tests.
Knip treats this directory as its own workspace so its dependencies are checked
against this package's manifest; keep that workspace registration while the
adapter exists.

Run `npm run lint:architecture` for the adapter's expected-result regressions and
the existing positive/negative boundary tests. The regressions also check actual
consumer module resolution, original engine version, absence of braces in the
lockfile, unsupported APIs, and bounded deep-nesting cases. They deliberately do
not install vulnerable micromatch as a test dependency. Validate a fresh `npm ci`,
`npm ls --all`, and full `npm audit` as well; audit results alone cannot establish
that local package links are usable. The frontend Dockerfile already copies
`scripts/` before both full and production-only dependency installations. Its
builder stage also copies the installed adapter directory from the dependency
stage: the adapter's picomatch lives in its own nested `node_modules/`, which the
later source copy excludes. Copying only root `node_modules/` would silently
select the unrelated root picomatch 4.x engine. A packaging regression models
these transfers and checks the resolved version and known engine differences.

Remove this adapter, its devDependency alias, scoped override, Knip workspace,
and adapter-specific tests when a reviewed upstream boundary dependency chain removes braces or uses
a patched release. Regenerate the lockfile, confirm the vulnerable dependency is
absent or patched, and rerun the unchanged architecture enforcement tests, full
frontend checks, fresh full and production-only installs, and audit before removal.
