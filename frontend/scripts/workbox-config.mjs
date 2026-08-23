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
 * The precache set is intentionally kept below a conservative browser
 * CacheStorage budget for the cross-browser E2E matrix. Firefox and
 * WebKit can reject a service-worker install when optional lazy chunks push
 * the manifest over that quota, even though Chromium accepts the same build.
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
 * The map page follows the same lazy-loading contract. MapLibre and the map
 * route chunks are only fetched when the user opens `/map`; keeping them out
 * of install-time precaching prevents a 1+ MB optional feature from consuming
 * the browser's offline storage budget. They remain available through the
 * normal network fetch path whenever the map is opened online.
 *
 * Wave 116 SW-Stretch raised maximumFileSizeToCacheInBytes from 2 MB → 5 MB
 * to unblock `build-storybook` (Storybook's sb-manager/globals-runtime.js
 * is 3.25 MB). That per-file limit remains independent from the smaller
 * aggregate browser CacheStorage budget handled by the map exclusions above.
 *
 * `offline.html` stays in the precache manifest. The project uses a custom
 * `injectManifest` worker (rather than Workbox's generated runtime routes),
 * so precaching the fallback is the only engine-independent guarantee that a
 * direct offline navigation can be served by Firefox and WebKit as well as
 * Chromium.
 */

/**
 * Keep a safety margin below the conservative CacheStorage budget exercised
 * by Firefox/WebKit in CI. This is an aggregate limit; Workbox's
 * `maximumFileSizeToCacheInBytes` only protects individual files.
 */
export const MAX_PRECACHE_BYTES = 4_800_000

/**
 * The Chromium E2E coverage job deliberately builds an unminified bundle so
 * V8 can map executed ranges back to readable source. That diagnostic bundle
 * is not a deployable production artifact and is substantially larger than
 * the minified browser build. Keep a separate, explicit ceiling for that
 * opt-in job instead of weakening the production budget.
 */
export const MAX_DIAGNOSTIC_PRECACHE_BYTES = 9_000_000

export const getPrecacheBudget = (env = process.env) => {
  const isE2ECoverageDiagnosticBuild =
    env.E2E_COVERAGE === "true" && env.FRONTEND_BUILD_UNMINIFIED === "true"
  return isE2ECoverageDiagnosticBuild
    ? {
        bytes: MAX_DIAGNOSTIC_PRECACHE_BYTES,
        label: "E2E diagnostic browser budget",
      }
    : {
        bytes: MAX_PRECACHE_BYTES,
        label: "browser budget",
      }
}

/** Apply the same transform logic against an explicit environment in tests. */
export const enforcePrecacheBudgetForEnv = (manifestEntries, env = process.env) => {
  const totalBytes = manifestEntries.reduce((total, entry) => total + (entry.size ?? 0), 0)
  const { bytes: activePrecacheBudget, label: budgetLabel } = getPrecacheBudget(env)
  if (totalBytes > activePrecacheBudget) {
    throw new Error(
      `Workbox precache is ${totalBytes} bytes, above the ${activePrecacheBudget}-byte ${budgetLabel}`
    )
  }
  return { manifest: manifestEntries }
}

/** @type {import("workbox-build").ManifestTransform} */
export const enforcePrecacheBudget = (manifestEntries) =>
  enforcePrecacheBudgetForEnv(manifestEntries, process.env)

/** @type {import("workbox-build").InjectManifestOptions} */
export const PWA_INJECT_CONFIG = {
  globPatterns: ["**/*.{js,css,html,ico,png,svg,webp,json}"],
  globIgnores: [
    "**/bundle-stats.*",
    "**/jspdf*.js",
    "**/html2canvas*.js",
    "**/purify*.js",
    // MapLibre is a lazy route; excluding its vendor/runtime chunks keeps
    // Firefox/WebKit service-worker installation within CacheStorage quotas.
    "**/vendor-map-*.js",
    "**/vendor-map-*.css",
    "**/Map-*.js",
    "**/MapFeature-*.js",
    "**/MapLibreMap-*.js",
    "**/map-*.js",
  ],
  maximumFileSizeToCacheInBytes: 5_000_000,
  manifestTransforms: [enforcePrecacheBudget],
}
