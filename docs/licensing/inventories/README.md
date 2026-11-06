# Dated component inventories

These snapshots accompany the [2026-11-06 audit](../AUDIT-2026-11-06.md).
They describe the development baseline and the audit's repairs, not a current
deployment or automatic legal approval. Version pins remain in the actual
lockfiles and image declarations. Workstation paths and redundant generated
checksums are omitted from these published evidence records.

| Inventory                      | Scope and interpretation                                                                                                                                                                 |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `repository-materials.json`    | Initial 5,502 tracked files: 30 package manifests, original notice paths, 154 skill directories and 152 asset/archive paths; manifest license fields refreshed after repairs             |
| `npm-locked-packages.json`     | Both npm locks, local target resolution, exact package/path roles and declared/effective license evidence; local links inherit their target metadata                                     |
| `python-locked-packages.csv`   | All 234 external uv lock records; 149 runtime-union and 85 development/tool-only records, metadata and actual legal-file evidence                                                        |
| `cargo-locked-packages.json`   | All seven Cargo locks, 557 records / 215 distinct name/version identities; legal metadata/text-file evidence                                                                             |
| `cargo-production-roles.json`  | Target-filtered production dependency graphs, runtime/build roles and legal text names; development/test-only records remain in the all-lock inventory                                   |
| `orjson-cargo-roles.csv`       | Exact orjson sdist's resolved runtime/build Rust dependencies across Windows/Linux/macOS; inactive lock-only records are excluded                                                        |
| `orjson-source-licenses.csv`   | Exact source files and SPDX headers; preserves the MPL versus Apache/MIT source boundary                                                                                                 |
| `go-module-graphs.tsv`         | All ten Go modules' MVS and checksum universes; includes entries that are not linked runtime code                                                                                        |
| `container-image-licenses.tsv` | 38 concrete image references, roles, declaration locations, upstream source/license evidence and unresolved OCI/base-layer provenance; three NATS defaults are disabled by parent values |
| `reference-skills.json`        | Full 415-file comparison against the upstream snapshot preceding import; subsequent local changes and unmatched material are explicit                                                    |

Runtime legal texts and exact-version source access are in
[distribution](../distribution/README.md). Browser JavaScript text coverage,
source recovery and optional/platform gaps are recorded in
[`frontend-runtime-source-index.json`](../../../frontend/public/licenses/javascript/frontend-runtime-source-index.json)
and the adjacent Linux optional-tooling index. Actual upstream legal-file
content is bundled separately from these metadata records.
