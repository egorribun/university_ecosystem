# Dependency Review capture adapter

The inputs and defaults in `action.yml` are copied and adapted from
[actions/dependency-review-action](https://github.com/actions/dependency-review-action).
The exact reviewed upstream commit and file identities are retained in
[`capture.cjs`](capture.cjs), in `UPSTREAM`. The upstream MIT notice is retained
verbatim in [`LICENSE-UPSTREAM`](LICENSE-UPSTREAM); copied upstream material
keeps that license. The two leading comments and local `mode`,
`upstream-commit`, `upstream-directory`, output declarations and runner changes
identify this repository's adaptation.

The adapter stages the separately checked-out upstream runner together with
its own `LICENSE` and `dist/licenses.txt`. Those original notices remain in
that staged distribution. New original adapter code is subject to the root
project terms, with earlier permissions preserved. These terms do not replace
upstream rights or change any Dependency Review policy or gate.
