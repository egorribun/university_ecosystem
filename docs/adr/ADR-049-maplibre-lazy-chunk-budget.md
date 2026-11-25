# ADR-049: Version-bound MapLibre lazy-chunk budget

- Status: Accepted scoped decision; implementation requires exact-source CI validation
- Owner: egorribun
- Decision approved: 2026-10-28 (MapLibre 6.15.0, 286 KiB)
- Revised: 2026-11-22 (MapLibre 6.18.0, 290 KiB)
- Revised: 2026-11-25 (MapLibre 6.19.0, 292 KiB)
- Scope: one MapLibre 6.19.0 client chunk

## Context

The production artifact at source `4b83ddc75b7c0842c38350351330e19dd2a634c2`
contains one MapLibre vendor chunk with 292,688 gzip bytes (285.83 KiB).
The existing analyzer now parses the emitted TanStack module-preload pair and
reports exactly one violation: that chunk exceeds the 280 KiB general lazy limit.
Keeping MapLibre 6.15.0 therefore requires an explicit 6 KiB increase for this
one proven chunk. This is a budget decision, not an optimization.

### Revision for MapLibre 6.18.0 (2026-11-22)

Dependabot #1548 proposed `maplibre-gl` 6.18.0. As this ADR requires for any
dependency upgrade, the 6.15.0 allowance stopped applying. A local production
build with 6.18.0 measured the vendor-map chunk at 296,360 gzip bytes
(289.41 KiB), using the analyzer's level-9 gzip measurement. That is above the
286 KiB ceiling. The
package exports and the three admitted module records are unchanged.

On 2026-11-22 the owner chose to raise the separate ceiling to 290 KiB for
exactly this version, rather than keep 6.15.0. All checks below stay as they
were. Only the bound version and the admitted ceiling change. The general
280 KiB lazy limit and every other ceiling are unchanged.

### Revision for MapLibre 6.19.0 (2026-11-25)

Dependabot #1588 proposed `maplibre-gl` 6.19.0 together with
`@maplibre/geojson-vt` 6.3.3. The 6.18.0 allowance therefore stopped applying.
A local production build with 6.19.0 measured the vendor-map chunk at 298,957
gzip bytes (291.95 KiB) with the same level-9 measurement. That is above the
290 KiB ceiling. The package exports and the three admitted module records are
unchanged. 6.19.0 also declares `zustand` ^5.1.0, which the application already
locks at 5.1.0. The package's `dist` files do not import it, and the build
metadata still lists only the three records below.

On 2026-11-25 the owner chose to raise the separate ceiling to 292 KiB for
exactly this version, rather than keep 6.18.0. As in the previous revision,
only the bound version and the admitted ceiling change.

The final-HTML inventory and compiler metadata are evidence inputs, not blanket
admission proofs. In particular, the observed 79 computed dynamic imports remain
unresolved. The decision below concerns static initial reachability only.

## Decision

The general lazy JavaScript limit remains 280 KiB. A separate 292 KiB ceiling
may apply to exactly one `assets/vendor-map-<build-id>.js` chunk only after all
checks below succeed for the artifact actually analyzed.

1. **Trusted build delivery.** The existing Production Build job publishes its
   validated schema-3 compiler metadata as a separate artifact outside `dist`.
   Its metadata content SHA-256, the existing final-HTML report content SHA-256,
   and server-issued artifact IDs are passed as build-job outputs. Bundle
   Analysis downloads the production bundle and both evidence artifacts by
   these exact IDs, within the current workflow run, with
   `digest-mismatch: error`. No extra permission or access token is introduced.

   The download action verifies archive bytes against the GitHub server digest
   for the selected artifact ID. It does not expose an `expected-digest` input
   and does not by itself compare a second upload-output digest. File-content
   hashes are checked separately against the build outputs. These are trusted
   GitHub Actions producer/consumer receipts, not an independently signed
   attestation.

2. **Same-source context.** The consumer verifies its checkout commit, tree and
   parent identities, run ID and attempt against the final-HTML capture. It
   rechecks the fixed source-file fingerprints and the compiler producer/Vite
   fingerprints against its own checkout. Claimed JSON context without this
   binding is insufficient.

3. **Exact package and composition.** Both the lock entry and installed package
   must identify `maplibre-gl` version `6.19.0`. Their integrity and manifest
   fingerprints must agree with the owned checkout and the installed package.
   Exactly one metadata candidate and one matching output vendor-map asset are
   permitted. The candidate must contain exactly these package module records,
   with canonical package roots and recomputed stable-ID hashes:

   - `dist/maplibre-gl.css` (zero rendered code units);
   - `dist/maplibre-gl.mjs`;
   - `dist/maplibre-gl-worker.mjs`.

   Extra, duplicate, foreign or missing records reject the allowance. Filename
   matching alone never grants it.

4. **Final artifact bytes.** The consumer rehashes every emitted graph chunk,
   including detached chunks, and both final HTML documents after download.
   Sizes, hashes, graph targets and document-root records must match the
   source-bound build evidence. The candidate's gzip bytes are recomputed with
   the analyzer's existing level-9 gzip measurement. Missing, changed, symlinked,
   malformed or inconsistent evidence rejects rather than falling back to a
   permissive path.

5. **Static initial reachability.** Starting from all compiler entries, all
   applicable roots in both final HTML documents and every direct literal
   static-import target, the consumer traverses the validated compiler static
   import graph independently. Graph edges come from the source-bound compiler;
   every non-root chunk is byte-verified, not independently reparsed. The
   candidate must be absent from that closure and from direct HTML references.
   Unknown static targets, unresolved static
   edges, parse errors, import maps, base overrides and unsupported root forms
   reject the allowance. The existing diagnostic `staticEntryReachable` and
   `complete` fields are not accepted as the verdict.

   The only permitted non-graph auxiliary files are `theme-init.js` and
   `static-shell-i18n.js`, each byte-identical to its corresponding tracked,
   clean `frontend/public/` source. Their paths must be disjoint from the
   compiler graph. Both must parse successfully: theme-init has no static or
   computed import and only its known literal dynamic edge to static-shell-i18n;
   static-shell-i18n has no imports. No other unknown root or static target is
   admitted by this auxiliary rule. These two tracked sources are included in
   the consumer's source-byte verification, not trusted by filename alone.

6. **Independent ceilings.** The admitted candidate is checked against 292 KiB.
   Every other general lazy asset is checked against 280 KiB, not only the
   previous maximum. Main-JS, initial-JS, CSS and password-dictionary ceilings
   remain unchanged. Absent evidence leaves the original 280 KiB rule active;
   supplied invalid evidence causes an explicit failure.

## Limits and consequences

Static-import non-reachability is not a proof that arbitrary runtime code cannot
dynamically request MapLibre early. Computed imports, handler execution, service
workers and network/cache scheduling are not proven by this decision. The
existing reports retain these limitations; no runtime-closure label is added.

The verifier operates on an owned, quiescent build/artifact directory under the
existing bounded CI job. No-follow reads and repeated fingerprints do not create
a universal filesystem-race sandbox. No existing timeout, worker, memory or
coverage limit is relaxed.

A dependency upgrade, changed module composition, duplicate vendor candidate,
initial static reachability or mismatched producer evidence invalidates this
allowance and requires a fresh decision. This does not authorize unrelated
dependency changes or exceptions.

## Validation evidence and activation boundary

At source `ed24ee867ace8f9804e6cdc6fa16cbe0ef416aca`, the selected native
contract cohort passed its original 142 cases and failed the three new positive
allowance assertions at the real 280 KiB check. Owned capture/provenance and
fixture gzip prerequisites succeeded; the synthetic candidate measured
282.51 KiB. Synthetic module records are contract inputs, not a substitute for
actual Rolldown compilation. The 29 negative mutations and both independent
ceiling variants were not reached in that RED run. Their later exact-source
execution and the separate real 285.83 KiB production artifact remain required.

For the 6.18.0 revision, the synthetic fixture stays inside the separate ceiling
at 282.51 KiB. Its oversized variant measures 291.93 KiB, so it still exceeds
290 KiB. The 289.41 KiB local measurement is not hosted evidence. The real
6.18.0 production artifact must pass the hosted Bundle Analysis job on the exact
source.

For the 6.19.0 revision, the admitted synthetic fixture is unchanged at
282.51 KiB. The oversized variant grows from 9,300 to 9,350 payload blocks and
measures 293.50 KiB, so it exceeds 292 KiB. The 291.95 KiB local measurement
is not hosted evidence either. The real 6.19.0 production artifact must pass
the hosted Bundle Analysis job on the exact source.

Required before treating the implementation as validated:

- Exact-source frontend lint, existing suites and focused budget tests pass.
- A real generated artifact passes the source/run/content/static-closure checks.
- Negative tests reject changed package versions, integrity, modules, source,
  run/attempt, artifact bindings, any graph/document byte, initial MapLibre
  reachability and missing/duplicate candidates.
- A non-Map lazy asset over 280 KiB still fails even when a larger admitted Map
  chunk is present; the Map chunk over 292 KiB also fails.
- Existing direct-HTML grammar, size ceilings and artifact catalog contracts
  remain enforced. No report-count or registry acceptance is inferred solely
  from this ADR.
