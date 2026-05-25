/**
 * workbox-config.mjs — single source of truth for vite-plugin-pwa
 * `injectManifest` options.
 *
 * Imported by:
 * - frontend/vite.config.mts (production VitePWA() invocation, dev mode +
 *   CI Linux full vite-plugin-pwa pipeline)
 * - frontend/scripts/build-orchestrated.mjs (Windows local standalone
 *   workbox-build.injectManifest invocation; vite-plugin-pwa is disabled
 *   via BUILD_SKIP_PWA=true env flag per W135 SW3 strategy)
 *
 * ## Why this exists
 *
 * Wave 135 SW3 introduced build-orchestrated.mjs which mirrored the
 * Workbox config inline (W135 §Honesty #5: "Workbox config drift risk").
 * If the Vite-side config drifted, dev mode + CI Linux builds used the
 * real plugin invocation with vite-config values, while
 * `npm run build` (Windows local) used the hard-coded mirror. Wave 136 SW6
 * eliminates the drift by extracting to this shared module.
 *
 * Verified BYTE-IDENTICAL bundle output post-extraction:
 * - dist/client/sw.js 53,181 bytes (same workbox manifest entries: 209 files,
 *   4.80 MB precached)
 *
 * ## Note on dynamic-import excluded chunks
 *
 * Wave 122 SW2 documented the rationale for excluding pdf-lib chunks from
 * precache. The chunks (jspdf, html2canvas, purify) are used ONLY by
 * Activity export + Schedule export via dynamic `await import()`.
 * Including them in __WB_MANIFEST forced the SW to fetch them on install
 * on every page load — Lighthouse `unused-javascript` counted those bytes
 * as wasted on /news, /events, and 5+ other routes.
 *
 * Wave 116 SW-Stretch raised maximumFileSizeToCacheInBytes from 2 MB → 5 MB
 * to unblock `build-storybook` (Storybook's sb-manager/globals-runtime.js
 * is 3.25 MB). Prod's largest precache entry is maplibre-gl-*.js (~1.03 MB),
 * well under 5 MB.
 */

/** @type {import("workbox-build").InjectManifestOptions} */
export const PWA_INJECT_CONFIG = {
  globPatterns: ["**/*.{js,css,html,ico,png,svg,webp,json}"],
  globIgnores: [
    "**/bundle-stats.*",
    "**/offline.html",
    "**/jspdf*.js",
    "**/html2canvas*.js",
    "**/purify*.js",
  ],
  maximumFileSizeToCacheInBytes: 5_000_000,
}
