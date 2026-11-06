# Third-party and separately licensed material

The proprietary [root notice](LICENSE) only applies to the restricted original
material it defines. It does not replace these licenses or earlier permissions.
This inventory covers known bundled material, not every transitive dependency
or distribution artifact.

| Material                                        | Retained notice or provenance                                                                                                                                            | License                                                                    |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------- |
| Earlier project publications                    | [Transition record](docs/licensing/README.md), [retained MIT notice](docs/licensing/legacy/LICENSE-MIT), and Git history                                                 | Existing MIT, ISC, and MIT/Apache-2.0 permissions remain applicable        |
| Unicode Emoji data                              | [Provenance](app/data/emoji/README.md), [notice](app/data/emoji/LICENSE.txt)                                                                                             | Unicode-3.0                                                                |
| Inter font files                                | [Notice](frontend/src/assets/fonts/OFL.txt)                                                                                                                              | SIL Open Font License 1.1                                                  |
| TanStack-derived view-transition implementation | [Inline upstream notice](frontend/src/app/routerViewTransitions.ts)                                                                                                      | MIT, Tanner Linsley and contributors                                       |
| Boundary micromatch compatibility adapter       | [Provenance](frontend/scripts/boundary-micromatch-compat/README.md), [notice](frontend/scripts/boundary-micromatch-compat/LICENSE)                                       | MIT, upstream notice retained                                              |
| React Compiler compatibility adapter            | [Notice](frontend/scripts/react-compiler-zod-compat/LICENSE)                                                                                                             | MIT, retained for this separately licensed developer tool                  |
| Minimatch 3 compatibility adapter               | [Metadata](frontend/scripts/minimatch-3-compat/package.json)                                                                                                             | ISC, retained for this separately licensed developer tool                  |
| MaxMind GeoIP test fixture                      | [Provenance](tests/fixtures/geoip/README.md), [notice](tests/fixtures/geoip/LICENSE-APACHE)                                                                              | Upstream Apache-2.0 or MIT; Apache-2.0 notice bundled                      |
| Bundled agent reference skills                  | Per-skill notices, including `.agents/skills/algorithmic-art/LICENSE.txt`, `.agents/skills/frontend-design/LICENSE.txt`, and `.agents/skills/webapp-testing/LICENSE.txt` | Respective upstream licenses; reference tooling, not original product code |

Installed Python, npm, Go, and Rust dependencies, container images, map data,
and external services remain governed by their applicable terms. Preserve
required notices, source availability, and attribution when distributing or
operating a product. Existing SBOM and dependency-license checks remain in
effect. This inventory is not a new dependency approval or a check exemption.

University names, logos, and imagery have not been verified as owned by
`egorribun`. No ownership, affiliation, endorsement, or permission to reuse
them is claimed here. Preserve existing map-data attribution, including
OpenStreetMap attribution.
