### Summary

When using chrome-devtools-mcp on Windows with headless Chrome to inspect heavy-DOM authenticated routes, the `Accessibility.getFullAXTree` and `Runtime.evaluate` CDP commands time out within their default windows (often 30-60s).

The timeout reproduces specifically:
- Windows host (not WSL)
- Headless mode
- Heavy DOM (e.g., > 500 elements, complex Framer Motion + glass shadow CSS, ParticleAuthBackground 1000-particle canvas)
- AXTree traversal OR JS evaluation

It does NOT reproduce on:
- Linux host (same routes work fine)
- macOS (same routes work fine)
- Windows + non-headless real Chrome (chromium playwright `channel: 'chrome'` works)

### Reproduction

1. Project structure (full repo on request):
   - React 19 + Framer Motion `domAnimation` LazyMotion config
   - 8 SSR routes (TanStack Start v1)
   - JWT auth with HttpOnly cookie + JWKS endpoint

2. Open chrome-devtools-mcp, navigate to authed dashboard route.

3. Try `take_snapshot()` (calls `Accessibility.getFullAXTree`) → timeout after default window.

4. Try `evaluate_script("document.body.innerText")` → timeout if DOM is heavy enough.

### Workaround

Use Playwright with `channel: 'chrome'` (real Chrome via WebSocket protocol layer, NOT chrome-devtools-mcp's CDP backchannel):

```js
const browser = await chromium.launch({ channel: 'chrome', headless: true })
```

Bypasses the CDP wall entirely. Documented in our repo at `frontend/scripts/playwright-visual-smoke.mjs` and `frontend/scripts/wave137-authed-smoke.mjs`.

### Environment

- OS: Windows 11 IoT Enterprise 10.0.26200
- Chrome: latest stable (139.x at time of writing)
- chrome-devtools-mcp: latest as of 2026-05-08

### Why this is hard

The CDP backchannel that chrome-devtools-mcp uses internally has different protocol semantics than the direct WebSocket DevTools connection Playwright opens. Some commands serialize through a proxy layer that adds round-trips → timeouts compound.

A "fix" would likely require chrome-devtools-mcp to either:
1. Expose a "raw CDP" mode that bypasses the proxy
2. Increase default timeouts for AXTree + Runtime.evaluate (they're often defaulted at 30s but heavy DOM needs 90s+)
3. Document the Windows + headless limitation and recommend Playwright as alternative
