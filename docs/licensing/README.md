# Licensing and the public source transition

The [root notice](../../LICENSE) provides proprietary public inspection terms
for future original material. The public rightsholder designation remains
`egorribun`. No additional personal details or public contact are specified.
No particular governing law or court is selected by this notice.

## Permissions

Visitors may read the source, exercise rights granted by GitHub's applicable
terms, and use owner-operated websites normally, including necessary browser
execution and caching, subject to access controls and separate service terms.
Additional use of restricted new material requires prior written permission:
this includes local builds and execution, self-hosting, modification, reuse,
redistribution, sale, and commercial or noncommercial use. Platform, statutory,
prior-license, and separate-authorization exceptions still apply.
Owner-authorized development and CI are not a public evaluation permission.

Issue reports and suggestions are welcome. External code or assets require a
separate executed contribution rights agreement before acceptance. A PR, DCO,
bot attribution, or repository access does not establish a transfer of rights.

## Existing code remains licensed

The root MIT notice was added at
[`765d0bd6461dc715e04996acbdefa087916d0dc3`](https://github.com/egorribun/university_ecosystem/commit/765d0bd6461dc715e04996acbdefa087916d0dc3)
on 2025-09-22. Commit
[`f5a29406716fa19ca20d9aa7ba481c296c10e0d6`](https://github.com/egorribun/university_ecosystem/commit/f5a29406716fa19ca20d9aa7ba481c296c10e0d6)
changed only its copyright year to 2026.

The pre-transition development snapshot is
[`9d4f55b0b54c990363d19af74b61a25a8f9a10bd`](https://github.com/egorribun/university_ecosystem/tree/9d4f55b0b54c990363d19af74b61a25a8f9a10bd).
The contemporaneous default-branch snapshot is
[`4963face79be2da224d28779433df7ef219deeb4`](https://github.com/egorribun/university_ecosystem/tree/4963face79be2da224d28779433df7ef219deeb4).
Both carry the root MIT notice retained verbatim in
[legacy/LICENSE-MIT](legacy/LICENSE-MIT).

At those snapshots, `frontend/package.json` declares ISC;
`native/rust_ext/Cargo.toml` declares `MIT OR Apache-2.0`;
`frontend/rust-crypto/Cargo.toml` and
`frontend/wasm-sanitizer/Cargo.toml` declare MIT. Those historical declarations
remain in Git and are not withdrawn by new package metadata.

The transition begins with publication of the new notice, not retroactively
at its version date or at the earlier snapshots. Any intervening material
published under the old terms keeps its permissions too. The notice only
restricts original material first published under it. Old code remains usable
and may be forked, modified, and distributed as its original license permits.
Unchanged old portions do not become restricted just because they occur in a
new checkout or package. Changing metadata alone does not stop anyone from
using the previously licensed product.

## Components and distribution

The [React Compiler adapter README](../../frontend/scripts/react-compiler-zod-compat/README.md)
is retained verbatim as part of its source-bound MIT component archive. Its
reference to the repository MIT license describes the earlier snapshot and
that separately licensed adapter, not a blanket license for new project
material. The component MIT notice and archive inputs remain unchanged.

[THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md) records known bundled
materials and separately licensed developer adapters. Their own notices take
precedence for those materials. Preserve dependency licenses, copyright notices,
and distribution obligations in each shipped artifact. This inventory is not
a complete transitive dependency compliance audit.

The project identifier is `LicenseRef-University-Ecosystem-Proprietary`.
Rust manifests identify that license; each crate bundles a `LICENSE` file.
Each production crate has
a local `.deny.exceptions.toml` permitting the identifier only for its exact
first-party package/version. Dependency license rules remain unchanged.
See [ADR-054](../adr/ADR-054-proprietary-public-source-terms.md).

Generated WASM packages carry the root notice. Existing licenses continue to
apply to their previously licensed program code and third-party dependencies;
the new package identifier does not override those rights.

Keep notices, README summaries, metadata, and contribution guidance consistent.
Review ownership and provenance before adding new material. Claim no rights
in university names, logos, or imagery whose ownership or permission has not
been verified. Enforceability depends on applicable law and actual ownership;
this record does not replace jurisdiction-specific legal review.
