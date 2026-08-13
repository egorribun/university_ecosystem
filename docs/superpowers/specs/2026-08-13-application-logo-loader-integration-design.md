# Application Logo Loader Integration Design

**Date:** 2026-08-13

**Status:** Approved design; written specification pending user review

**Related artifact:** `C:\Users\egorribun\Documents\logo-loader.html`

**Related specification:** `docs/superpowers/specs/2026-08-13-standalone-logo-loader-design.md`

## Purpose and scope

Integrate the approved logo animation into the University Ecosystem frontend as the initial application bootstrap screen. The loader must be visible in the server-rendered document before the JavaScript bundle executes, must not introduce a React hydration mismatch, and must leave as soon as the application reports that hydration has completed.

The integration is limited to the first document load. Client-side route changes continue to use the application's existing pending and loading states.

## Approved behavior

- Preserve the supplied SVG geometry and the solid brand colors navy `#033167` and red `#E40137`.
- Preserve the six-second automatic logo timeline: staggered construction, an exactly 2.5-second fully assembled hold during long loads, a shared 0.45-second mark fade, and a hidden reset gap.
- Do not add rocking, pulse, rotation, bounce, glow, or background-halo movement.
- Keep the visible status label `Загрузка` stationary and fully opaque throughout every automatic logo cycle. It must not disappear during the mark's shared fade or reset gap.
- Keep the ellipsis adjacent to the status label. Its dots may animate independently to communicate activity, but the status row itself must remain visible and must not shift.
- When application hydration completes, do not wait for the six-second logo cycle to finish. Fade the entire bootstrap overlay once, then remove it from interaction and rendering. This final overlay exit necessarily includes the status label; the requirement for a permanently visible label applies while loading is active and between logo cycles.
- Keep the standalone HTML as the framework-neutral reference and update it to use the same persistent-status behavior.

## Chosen architecture

Use a small SSR-safe React component rendered by the existing `RootShell` before the `#root` application container. Its initial markup and state are deterministic, so the server output and first client render are identical.

The component owns only the bootstrap overlay and its lifecycle. Critical loader CSS is emitted in the existing shell-level inline style path so the first paint never depends on a fetched stylesheet. The implementation reuses the verified SVG paths and timing constants from the standalone file; it does not embed the standalone document, its preview controls, or its public `window.logoLoader` API.

This approach is preferred over:

1. A client-only loader, which would appear after the bundle and could expose a blank first paint.
2. Separate CSS or JavaScript bootstrap assets, which would add requests and allow an unstyled flash.
3. An iframe or object embedding the standalone file, which would complicate accessibility, theming, CSP, and responsive sizing.

## Components and ownership

### `BrandBootLoader`

A focused component under `frontend/src/components/feedback/` renders:

- one fixed, full-viewport overlay;
- the exact inline SVG mark;
- an independent status row containing `Загрузка` and the ellipsis;
- stable accessibility attributes and test hooks;
- a post-hydration lifecycle listener with idempotent cleanup.

The logo's shared cycle fade is applied only to its common `.mark` group. The status row is outside that group and has no cycle-level opacity animation. The final application-ready exit is applied to the common overlay, ensuring that every visible element leaves together only when loading is actually complete.

### `RootShell`

`frontend/src/routes/__root.tsx` renders `BrandBootLoader` as a sibling immediately before `#root`. Loader styles are appended to the existing critical `INITIAL_PAINT_CSS` so they are available in the first server-rendered response and follow the established CSP-compatible shell path.

The loader uses a z-index below the existing LHCI diagnostic marker and above all application UI. It does not alter router fallbacks, suspense boundaries, or the provider tree.

### Hydration completion signal

`AppProviders` retains `window.__APP_HYDRATED = true` as the canonical post-commit sentinel and dispatches one namespaced completion event in the same effect. `BrandBootLoader` listens for that event and also checks the sentinel when its effect mounts, eliminating listener-order races.

The completion path is idempotent for React StrictMode. Repeated effects, repeated events, a transition event plus timeout fallback, or late completion after the failsafe cannot trigger duplicate state transitions or errors.

## Lifecycle and timing

1. The server emits the complete overlay, SVG, persistent status row, and critical CSS.
2. CSS starts the six-second logo animation without waiting for JavaScript.
3. The application hydrates beneath the fixed overlay.
4. `AppProviders` sets the existing hydration sentinel and dispatches the completion event.
5. `BrandBootLoader` immediately begins one shared 0.45-second overlay fade, without waiting for the current logo cycle boundary.
6. At transition completion, with a defensive timer fallback, the component becomes non-interactive and no longer renders.

The exit starts within one animation frame of the hydration signal. The normal completion path must finish within 600 ms of that signal.

A CSS-only 12-second failsafe hides the overlay if client JavaScript never mounts or hydration never reports completion. This prevents an infinite loader from masking server-rendered content or an application failure.

## Visual and responsive behavior

- Use the application's pre-paint `--initial-bg` value so light and dark first paint match the selected theme without a flash.
- Center the composition with fixed positioning, dynamic viewport units, and safe-area padding.
- Size the mark with bounded `clamp()` and viewport-relative values so it remains balanced at 320 px widths, short landscape screens, tablets, desktops, and 4K displays.
- Keep the SVG vector-based and preserve its aspect ratio at every device-pixel ratio.
- Reserve a stable status-row height so dot animation cannot cause layout movement.
- Keep the overlay self-contained and prevent horizontal overflow or scroll locking changes.

## Accessibility and reduced motion

- Expose one polite loading status, with `aria-atomic="true"` and localized visible text.
- Mark the decorative SVG and dots as hidden from assistive technology to avoid duplicate announcements.
- Do not add focusable controls or trap focus in the loader.
- The overlay intercepts pointer interaction only while it is active and releases it when final exit begins.
- Under `prefers-reduced-motion: reduce`, show the complete static logo, the static `Загрузка...` status, and skip all construction and dot animation. Completion removes the overlay without decorative motion.
- Announce loading once; animation cycles must not repeatedly update the accessibility tree.

## Error handling and compatibility

- Use React, inline SVG, CSS animations, and browser events already supported by the frontend; add no dependency or network request.
- Guard DOM and timer cleanup so unmounting, page visibility changes, strict effects, and transition cancellation cannot throw.
- Pause the logo timeline while the page is hidden when client code is available; resume from the same phase when visible.
- Keep the CSS-only animation and 12-second failsafe functional when JavaScript is unavailable.
- Do not mutate `#root` markup during hydration or insert elements imperatively before hydration finishes.

## Verification strategy

### Static and unit checks

- Verify exact SVG paths, colors, master timing, 2.5-second hold, and the absence of mark transforms.
- Verify that the status row is outside the animated mark and has no cycle opacity animation.
- Verify SSR markup, default theme state, accessible status semantics, and shell ordering.
- Verify hydration completion, already-hydrated listener races, StrictMode duplicate effects, transition fallback, failsafe, cleanup, and reduced-motion behavior with deterministic tests.
- Extend the existing `RootShell` and `AppProviders` tests rather than creating overlapping test harnesses.

### Build and browser checks

- Run frontend formatting, linting, targeted Vitest tests, TypeScript type checking, and a production build.
- Inspect the generated shell for loader markup, critical CSS, CSP nonce handling, and absence of unexpected external assets.
- Run Playwright checks at 320×568, 568×320, 768×1024, 1440×900, and 3840×2160 in light and dark themes.
- Exercise fast hydration, delayed hydration lasting through a full logo cycle, reduced motion, background-tab pause/resume, and the 12-second failsafe.
- Confirm there are no console errors, React hydration warnings, horizontal overflow, content flash, blocked controls after exit, or lingering overlay hit target.
- Compare the assembled logo visually against the supplied source image and the verified standalone reference.

## Acceptance criteria

1. The loader is visible and correctly styled in the first server-rendered paint without waiting for application JavaScript.
2. Initial server markup hydrates without React warnings or recoverable errors.
3. The assembled logo matches the supplied geometry and exact navy/red colors.
4. No whole-logo rocking or transform animation exists.
5. During a sufficiently slow load, the full logo remains static for exactly 2.5 seconds per six-second cycle.
6. Navy and red use one common mark opacity for every cycle exit.
7. `Загрузка` remains continuously visible and stationary through logo fade and reset phases.
8. Hydration triggers the final overlay exit immediately; it does not wait for the current animation cycle.
9. The overlay is gone and no longer blocks interaction within 600 ms of the hydration signal.
10. Reduced-motion, no-JavaScript, delayed-hydration, StrictMode, and 12-second-failsafe paths behave as specified.
11. Layout and rendering pass the listed phone, landscape, tablet, desktop, and 4K viewports without clipping or overflow.
12. The integration adds no runtime dependency, external asset request, route-level loader replacement, or hydration-sensitive imperative insertion.

## Out of scope

- Replacing route-level skeletons, suspense fallbacks, or data-loading indicators.
- Showing the bootstrap loader during client-side navigation.
- Adding real network-progress estimation to the application integration.
- Adding decorative effects beyond the approved Clean Signature direction.
- Refactoring unrelated SSR, router, provider, or CSP infrastructure.
