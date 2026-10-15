# Root semantic-release micromatch subset

This package deliberately identifies as `micromatch@4.0.8` only to satisfy the semver ranges used by the repository's two root developer-tool consumers. It is not a general drop-in replacement for the micromatch API.

## Audited consumers

- `semantic-release/lib/branches/expand.js` calls the default export as `micromatch(gitBranches, branch.name)`. The repository release config uses the literal branch pattern `main`.
- `@semantic-release/commit-analyzer/lib/analyze-commit.js` calls only `.isMatch(object, src)` for string-valued default release-rule fields. The repository does not define custom `releaseRules`; its patterns are literals such as `feat`, `fix`, and `perf`.
- The root dependency graph has exactly those two `micromatch` consumers. This conclusion is tied to the lock graph and source inventory at the candidate base revision; review the graph again if root tooling dependencies change.

The implementation provides only those two functions. APIs such as `match`, `not`, `matcher`, `braces`, `capture`, and `parse` are intentionally absent. Options outside the small explicit picomatch-compatible subset are rejected; unsupported consumers or options must be addressed before this package can be broadened.

## Resource bounds and behavior contract

Inputs are bounded to 10,000 candidate strings, 256 patterns, 4,096 UTF-16 code units per pattern, and nesting depth 64 for braces and extglobs. Violations throw before the regex engine runs. Contract tests cover literal and glob patterns, brace alternation/ranges, extglob and negative patterns, dotfiles, case handling, globstar, ignore, and the limited option set. A separate oracle pass compared the supported cases to the installed upstream `micromatch@4.0.8`.

This adapter removes the root toolchain's `micromatch -> braces@3.0.3` edge. The official advisory [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) lists `braces <=3.0.3` as affected and has no patched version; the package is therefore not retained behind an exception or audit allowance.

The frontend boundary compatibility adapter is a separate package and remains unchanged by this root-only candidate.
