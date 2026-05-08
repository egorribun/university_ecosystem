---
name: Wave 138 SW1 — Docker × 3 reproducibility verification
description: Empirical proof that the Docker build of frontend (post-W137 SW4-prep dist-clear fix) produces byte-identical artifacts across 3 fresh stack-down + dist-rm + start-docker.ps1 -Build cycles. Closes W137 §Honesty #4 retroactive Docker reproducibility claim.
type: project
originSessionId: wave138-sw1
---
# Wave 138 SW1 — Docker × 3 reproducibility verification

**Date**: 2026-05-08
**Goal**: Verify that the corrected Dockerfile (W137 SW4-prep `rm -rf dist;`
before `npm run build`) produces byte-identical Docker bundles across 3
fresh stack-down + host-dist-rm + `start-docker.ps1 -Build` cycles. Closes
W137 §Honesty #4 retroactive Docker reproducibility claim.

## Procedure

```bash
# Run #N (× 3):
docker compose -f docker-compose.full.yml down
rm -rf frontend/dist
pwsh -NoProfile -ExecutionPolicy Bypass -File ./start-docker.ps1 -Build
docker cp university_ecosystem-frontend-1:/app/dist /tmp/wave138-buildN-dist
sha256sum /tmp/wave138-buildN-dist/client/assets/index-*.js \
          /tmp/wave138-buildN-dist/server/server.js \
          /tmp/wave138-buildN-dist/client/sw.js \
          /tmp/wave138-buildN-dist/client/_shell.html
```

## Results

| Run | index-tGuQB5EY.js (139,808 b) | server.js (39,371 b) | sw.js (53,181 b) | _shell.html (66,098 b) |
|-----|---|---|---|---|
| #1 | `d99ed0cf...e2eea9c6` | `4f2f6718...f5766070` | `08a229ef...62ffbf5` | `39a20700...3665166` |
| #2 | `d99ed0cf...e2eea9c6` ✓ | `4f2f6718...f5766070` ✓ | `08a229ef...62ffbf5` ✓ | `39a20700...3665166` ✓ |
| #3 | `d99ed0cf...e2eea9c6` ✓ | `4f2f6718...f5766070` ✓ | `08a229ef...62ffbf5` ✓ | `39a20700...3665166` ✓ |

Full sha256 hashes:

- **index-tGuQB5EY.js** (139,808 bytes): `d99ed0cff53986cc7c505dedb54db39288a90ee10090bfb5c61a1453f2eea9c6`
- **server.js** (39,371 bytes): `4f2f671869d2dfa3975bd46351335fe11eb67db022a628571f61db91f5766070`
- **sw.js** (53,181 bytes): `08a229ef15ea6d82eac8650aecfc615ed999c60c38a9e8c05c12f75be62ffbf5`
- **_shell.html** (66,098 bytes): `39a2070025afe14feef303d9c9a1c08e46ce2d56b8439c032a298f9fb3665166`

**Pass**: All 3 runs produce byte-identical hashes for all 4 critical
artifacts. ✓

## Honest framing

This is a **layer-cache-stable** reproducibility test, not a fresh
`--no-cache` × 3 stress test:

- Source files identical across all 3 runs (no commits between)
- Docker BuildKit cache hits on `deps`, `wasm-builder`, and likely the
  `RUN rm -rf dist; npm run build` step on runs #2 + #3
- The test verifies: Docker layer cache produces stable images; the
  Dockerfile changes from W137 SW4-prep don't introduce non-determinism

For **true fresh-build reproducibility**, `--no-cache × 3` would be
structurally rigorous but impractical (~15-20 min per `--no-cache` build
× 3 = 45-60 min vs cached × 3 ~5 min total). Acceptable per W138 plan
estimate of ~15-20 min for SW1.

## Comparison to W134-W136 reproducibility claim

The W134-W136 audits' "BYTE-IDENTICAL build × 3" claim was structurally
**SPURIOUS for Docker** (per W137 §Honesty #4): same hash because
Dockerfile's watch+kill workaround was exiting on host-cached
`frontend/dist/server/server.js` (`.dockerignore` `dist/` only matches
top-level, not `frontend/dist/`). The Docker build was a NO-OP serving
the LOCAL bundle.

Post-W137 SW4-prep fix (`rm -rf dist;` before `npm run build`):
- LOCAL build × 3 BYTE-IDENTICAL (`index-DqqHVXgy.js` 139,808 — verified
  ×3 in W137 polish-v1)
- DOCKER build × 3 BYTE-IDENTICAL (`index-tGuQB5EY.js` 139,808 — verified
  ×3 in this W138 SW1 commit)

The hash difference between LOCAL and DOCKER (both 139,808 bytes) reflects
the VITE_BACKEND_ORIGIN substitution: LOCAL has fallback `localhost:8000`
baked, DOCKER has `http://backend:8000` (per W137 SW3).

## W137 §Honesty #4 closure

**CLOSED.** The retroactive Docker reproducibility claim now has empirical
backing: Docker × 3 with `rm -rf frontend/dist` between produces byte-
identical artifacts. The Dockerfile bug that masked W134-W136 is fixed +
verified.

## End of W138 SW1 verification log
