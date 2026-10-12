# Merge exceptions (break-glass log)

Every merge into `main` that uses the Admin bypass of ruleset `8335285` is
recorded here, as required by [AGENTS.md §5](../../AGENTS.md#5-merge-policy).
A bypass needs an explicit owner authorization for the named pull requests.

| Date (UTC) | Pull requests | Unsatisfied checks | Reason | Approved by |
| --- | --- | --- | --- | --- |
| 2026-10-12 10:15–10:17 | #1315 handlebars 4.7.10 (`52fbb2439`), #1316 compression 1.8.2 (`486263322`), #1317 smol-toml 1.9.1 (`96ecf45ea`), #1318 brace-expansion 1.1.21 (`2f4de04dd`), #1319 source-map-js 1.2.2 (`b6119feb6`), #1320 dompurify 3.4.16 (`e329f8ab8`), #1321 proxy-addr 2.0.8 (`ac74e915a`) | Required checks of `main` not green (`CI Success` failing on the pre-existing `main` baseline) | Dependabot dependency updates, including the handlebars security fix (3 GHSA); handlebars merged before the 7-day cooldown ended | Owner, explicit authorization in session; cooldown exception per [DEPENDENCY_COOLDOWN_EMERGENCY.md](../DEPENDENCY_COOLDOWN_EMERGENCY.md) |

Squash merges were performed one at a time; no branch was edited and no
conflict needed manual resolution. Merges before 2026-10-12 are not
reconstructed here; the owner decided not to re-classify them.
