# Standalone Logo Loader Design

**Date:** 2026-08-13

**Status:** Approved direction; written specification pending user review

**Output:** `C:\Users\egorribun\Documents\logo-loader.html`

## Purpose and scope

Produce one dependency-free HTML file that can be opened directly for preview or integrated into a web application. The loader preserves the supplied logo geometry, displays the fully assembled logo for exactly 2.5 seconds, removes whole-logo rocking, and fades both colored halves simultaneously.

The selected visual direction is **A — Clean Signature**. Glow and background-halo treatments from directions B and C are intentionally excluded from the default design.

## Visual design

- Use the source image's solid colors: navy `#033167` and red `#E40137`.
- Preserve the current SVG paths and the 0.45-second red-entry offset.
- Draw each colored half as normalized SVG strokes, then dissolve the construction stroke into the final fill. This prevents the completed silhouette from becoming thicker than the original artwork.
- Start the first and second inner accent lines 70 ms and 140 ms after their half's body so the drawing order remains legible without moving the completed logo.
- Apply `translate(0.45%, 0.15%)` as the default optical placement adjustment while leaving the SVG geometry unchanged.
- Keep the background visually neutral in the default light theme. No pulse, rocking, rotation, bounce, glow, or decorative halo is permitted.

## Automatic animation timeline

One six-second master timeline drives every animated element. Red's delay is encoded inside that timeline rather than applied as a delayed copy, so entry can remain staggered while exit is shared.

| Phase | Time | Behavior |
| --- | ---: | --- |
| Navy construction | 0.00–2.16 s | Outer body and accents draw, then resolve into fill |
| Red construction | 0.45–2.61 s | Same construction sequence, offset only on entry |
| Completed hold | 2.61–5.11 s | Both halves remain completely static for exactly 2.5 s |
| Shared exit | 5.11–5.56 s | One parent opacity animation fades both halves together |
| Reset gap | 5.56–6.00 s | Logo remains hidden while paths reset for the next cycle |

The status dots use the same master duration: they appear sequentially during construction, remain visible during the completed hold, and fade with the logo.

## Responsive layout

- Center the loader within the available viewport using dynamic viewport units and safe-area padding.
- Scale the mark with `width: clamp(9rem, 22vmin, 18rem)`, giving an exact 144–288 px range at the default 16 px root size.
- Scale gap and status typography independently so the loader remains balanced on narrow phones, landscape screens, tablets, desktop displays, and 4K screens.
- Prevent horizontal overflow at 320 CSS pixels and vertical clipping in short landscape viewports.
- Keep the SVG vector-based and sharp at every device-pixel ratio.

## Themes and embedding

The root loader accepts `data-theme="light"`, `data-theme="dark"`, or `data-theme="transparent"`. The default is light. Theme colors, master duration, sizing, spacing, and optical offsets are exposed as documented CSS custom properties; phase percentages remain fixed to preserve the approved 2.5-second hold.

The standalone file uses a full-viewport preview by default. Its loader element remains self-contained so the same markup can be placed inside another positioned container without external assets or network requests.

## Integration API

The file exposes `window.logoLoader` after `DOMContentLoaded`:

- `setProgress(percent)` clamps `percent` to `0..100`, switches to determinate mode, updates ARIA progress information and status text, and maps real progress to stroke drawing and final fills. The completed logo is reached only at 100%.
- `startAutomatic()` returns to the six-second looping animation.
- `complete()` returns a Promise. In automatic mode it lets the active cycle reach its hidden reset boundary before hiding the loader. In determinate mode it renders 100%, holds the completed logo for 2.5 seconds, performs the shared 0.45-second fade, then hides it.
- `restart(options)` reveals and resets the loader; `options.automatic` defaults to `true`.
- `setTheme(theme)` accepts only `light`, `dark`, or `transparent` and returns the applied theme.

Completion is idempotent. The root dispatches a `logo-loader:complete` event after it becomes hidden. Invalid progress values are ignored without breaking the automatic fallback.

## Accessibility and lifecycle behavior

- Automatic mode uses an accessible status region with localized loading text.
- Determinate mode exposes progress-bar semantics, `aria-valuemin`, `aria-valuemax`, and `aria-valuenow`.
- `prefers-reduced-motion: reduce` shows a fully assembled static logo and static status dots. Completion hides the loader on the next animation frame without adding motion.
- Animations pause while `document.hidden` is true and resume without losing phase when the page becomes visible.
- If JavaScript is unavailable, the CSS automatic loader continues to work.

## Error handling and compatibility

- Use standards-based HTML, inline SVG, CSS animations, and small defensive JavaScript; do not use libraries, external fonts, images, or runtime downloads.
- Guard all DOM access and public methods so integration calls cannot throw because the loader was already completed or removed from layout.
- Keep a static fallback for browsers that do not support the Web Animations API; core automatic animation is CSS-only.

## Verification and acceptance criteria

1. The standalone file opens without console errors or network requests.
2. Both halves are fully visible together for 2.5 seconds per automatic cycle.
3. Both halves begin and finish fading at the same time.
4. The assembled mark has no transform animation and matches the supplied geometry and sampled colors.
5. Automatic, determinate, completion, restart, theme, background-tab, and reduced-motion states work as specified.
6. The page has no horizontal overflow and remains centered at 320×568, 568×320, 768×1024, 1440×900, and 3840×2160 CSS-pixel viewports.
7. The final HTML remains a single clean, readable, dependency-free file ready for integration.

## Out of scope

- Modifying application source files in `university_ecosystem`.
- Adding glow, animated halo, whole-logo movement, sound, or external branding assets.
- Assuming a specific framework lifecycle; integration remains framework-neutral.
