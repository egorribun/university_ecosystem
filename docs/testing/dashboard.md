# Quality dashboard

The quality dashboard is no longer committed to this repository. The scheduled
**Quality History** workflow (`.github/workflows/quality-history.yml`, protected
`main` only) renders it from the certified CI quality manifests of recent
successful runs. The live dashboard is published in two places:

- the job summary of each Quality History run (Actions, then Quality History,
  then the run, then Summary); and
- the workflow artifact `quality-history-<source-sha>-attempt-<run-attempt>`,
  which contains `dashboard.md` and the `quality-history/` manifests it links
  to. The artifact is retained for 90 days.

The workflow has read-only repository permissions. It does not commit, push or
open pull requests.

A `—` in the rendered dashboard means evidence was not observed. It is never a
passing score. Historical CI-capacity observations are diagnostic context only,
not current release evidence. Release evidence is defined by
[ADR-047](../adr/ADR-047-risk-based-quality-policy.md) and the required checks in
[`quality/release-required-checks.json`](../../quality/release-required-checks.json).
