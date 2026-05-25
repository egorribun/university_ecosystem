// Wave 125 Phase 2 — post-build HTML processing for the TanStack Start
// spa-shell-rendered `dist/client/_shell.html` (rather than the
// pre-W125 `dist/index.html` produced by Vite's standard SPA pipeline).
// Runs as a separate npm script chained after `vite build` to avoid the
// Windows shell:true child-process issue where parent script exits
// before post-process logic in the same process can run.
//
// Four things happen here:
//   1. Inject critical font preload links (W124 SW2 — `inter-cyrillic`
//      + `outfit-latin` woff2 variants). The Vite plugin
//      `withFontPreload()` in `vite.config.mts` only fires on
//      `transformIndexHtml`, which TanStack Start's spa shell skips
//      because it generates the HTML via React SSR. Re-implementing
//      here keeps the FOIT-reduction win from W124 SW2 alive.
//   2. CSP nonce placeholder injection (replaces W125-Phase-1 reliance
//      on the `withStrictCspNonce` Vite plugin, which also bound to
//      `transformIndexHtml` and thus does not fire on the React-SSR
//      shell). Adds `nonce="__CSP_NONCE__"` to every `<script>` tag in
//      the shell so the FastAPI CSP middleware can swap in a per-
//      request nonce, preserving the strict-dynamic CSP posture from
//      DEBT-05 (audit 2026-03-06).
//   3. VITE_LHCI placeholder replacement (kept from pre-W125
//      `run-build.mjs`). The LHCI marker + visibility CSS are needed
//      because the spa-shell-served HTML must allow Lighthouse to see
//      a paint as soon as scripts evaluate.
//   4. Mirror the prerendered shell to `dist/client/index.html` so
//      that static serving (e.g. `staticDistDir: dist/client` for LHCI,
//      `npx serve dist/client -s` for local SPA-style preview) finds
//      the shell at the conventional `index.html` path.

import { copyFileSync, existsSync, readdirSync, readFileSync, writeFileSync } from "node:fs"
import path from "node:path"
import process from "node:process"

const FONT_PRELOAD_PATTERN = /^(inter-cyrillic-wght-normal-|outfit-latin-wght-normal-)[^/]*\.woff2$/

const CSP_NONCE_PLACEHOLDER = "__CSP_NONCE__"

function findShellHtml(cwd) {
  // Wave 131 Phase 4 — Nitro plugin restructured outputs from `dist/client/`
  // to `.output/public/`. Both paths are checked so this script keeps
  // working across pre-W131 (no Nitro) and W131+ (Nitro) builds without
  // forcing a flag-day. .output/public/ is checked first because that's
  // the canonical Nitro path; dist/client/ remains as a fallback for any
  // build pipeline variant that doesn't go through Nitro.
  const candidates = [
    path.join(cwd, ".output", "public", "_shell.html"),
    path.join(cwd, ".output", "public", "index.html"),
    path.join(cwd, "dist", "client", "_shell.html"),
    path.join(cwd, "dist", "client", "index.html"),
    path.join(cwd, "dist", "_shell.html"),
    path.join(cwd, "dist", "index.html"),
  ]
  for (const candidate of candidates) {
    if (existsSync(candidate)) return candidate
  }
  return null
}

function findCriticalFontFiles(assetsDir) {
  if (!existsSync(assetsDir)) return []
  return readdirSync(assetsDir)
    .filter((file) => FONT_PRELOAD_PATTERN.test(file))
    .sort()
}

function injectCspNoncePlaceholders(html) {
  // PERF-W16-02 / DEBT-05 — every `<script>` tag without an existing
  // `nonce=` attribute gets a `__CSP_NONCE__` placeholder. The FastAPI
  // CSP middleware (`app/core/policies/csp.py`) replaces this placeholder
  // per-request with a base64 nonce that matches the response's
  // Content-Security-Policy header, enabling strict-dynamic CSP.
  // dotAll (s) flag handles multi-line script attributes.
  return html.replace(/<script\b(?![^>]*\bnonce=)[^>]*>/gis, (tag) => {
    const insertion = tag.indexOf("<script") + "<script".length
    const before = tag.slice(0, insertion)
    const after = tag.slice(insertion)
    return `${before} nonce="${CSP_NONCE_PLACEHOLDER}"${after}`
  })
}

function injectFontPreloads(html, fontFiles) {
  if (fontFiles.length === 0) return html
  // The shell's <head> always closes with `</head>` — append our preload
  // links right before that close tag so they execute before <body>
  // styles are computed (browser font loader queues them earlier).
  const preloadLinks = fontFiles
    .map(
      (font) =>
        `<link rel="preload" as="font" type="font/woff2" crossorigin href="/assets/${font}"/>`
    )
    .join("")
  return html.replace("</head>", `${preloadLinks}</head>`)
}

// W150 polish-followup — strip React Suspense boundary markers from <div id="root">
// when shell has NO server-rendered content (root ssr:false or build-time-only SSR
// pass produced empty Outlet). TanStack Start's build emits the markers as a
// placeholder for streaming Suspense, but when client uses createRoot() (no SSR
// content to hydrate), the markers register as comment-node children which
// confuse hydrateRoot if anyone uses it. main.tsx checks hasChildNodes() to
// decide hydrate vs create — comment markers make that check incorrect. Stripping
// markers normalises the empty root to `<div id="root"></div>` so hasChildNodes()
// correctly returns false → createRoot path → no hydration mismatch.
//
// Only applied when ROOT IS NOT SSR-RENDERED (heuristic: no `data-rh` or other
// react helmet attributes near root indicating real SSR content). For now,
// unconditional strip works because shell is the SAME static file for all routes;
// per-route SSR is handled at runtime via tanstackStart's handler.fetch, not via
// the shell file.
function stripEmptySuspenseMarkers(html) {
  // W150 polish-followup — strip ALL content from <div id="root"> when running
  // in DEV_NO_SSR_SHELL mode (env var). This converts the SSR-prerendered shell
  // into a classic empty-SPA shell so client createRoot() mounts from scratch
  // without hydration mismatch. Production SSR builds skip this strip and
  // hydrate the SSR content (W125 Phase 5 hydrateRoot path).
  //
  // Hydration mismatch sources we cannot easily fix without dev-mode source maps:
  //   - useId() reconciliation differences SSR vs client
  //   - React Suspense boundary placeholder timing
  //   - LiveRegion + other portals in MainLayout
  //   - Provider tree differences between SsrRoot + RootComponent branches
  //
  // The strip is intentionally LOSSY for SSR perf but resolves React error #418
  // which blocks all routes on the local Docker stack. W151+ candidate to
  // root-cause via NODE_ENV=development build and unminified error messages.
  if (process.env.DEV_NO_SSR_SHELL === "1") {
    return html.replace(/(<div id="root"[^>]*>)[\s\S]*?(<\/div>\s*<noscript)/, "$1$2")
  }
  // Default: just strip the empty-suspense markers pattern (safe always).
  return html.replace(
    /<div id="root">\s*<!--\$-->\s*<!--\/\$-->\s*<\/div>/g,
    '<div id="root"></div>'
  )
}

function applyLhciReplacements(html, isLHCI) {
  if (isLHCI) {
    const lhciStyles =
      "html, body, #root { background: #FFFFFF !important; color: #000000 !important; " +
      "opacity: 1 !important; visibility: visible !important; } " +
      "#lhci-marker { display: flex !important; }"
    return html.replace("/* LHCI_CSS_PLACEHOLDER */", lhciStyles).replace(/%VITE_LHCI%/g, "true")
  }
  return html.replace("/* LHCI_CSS_PLACEHOLDER */", "").replace(/%VITE_LHCI%/g, "false")
}

function main() {
  const cwd = process.cwd()
  const shellPath = findShellHtml(cwd)
  if (!shellPath) {
    console.warn(
      "Post-build: no spa shell HTML found in .output/public/ or dist/. " +
        "Skipping font preload + CSP + LHCI replacements."
    )
    return
  }

  const isLHCI = process.env.VITE_LHCI === "true"
  const assetsDir = path.resolve(path.dirname(shellPath), "assets")
  const fontFiles = findCriticalFontFiles(assetsDir)

  let html = readFileSync(shellPath, "utf8")
  const originalSize = html.length
  html = injectCspNoncePlaceholders(html)
  html = injectFontPreloads(html, fontFiles)
  html = applyLhciReplacements(html, isLHCI)
  html = stripEmptySuspenseMarkers(html)
  writeFileSync(shellPath, html, "utf8")

  // Mirror the post-processed shell to `index.html` in the same directory
  // so static-server fallbacks (LHCI's staticDistDir, `npx serve -s`, etc.)
  // serve the spa shell on the conventional index path. This lets the
  // existing LHCI infrastructure (which expects `dist/.../index.html`) work
  // unchanged and lets `npx serve dist/client -s` behave like a SPA.
  let mirrorPath = null
  if (path.basename(shellPath) !== "index.html") {
    mirrorPath = path.join(path.dirname(shellPath), "index.html")
    copyFileSync(shellPath, mirrorPath)
  }

  console.log(`Post-build: shell ${shellPath} processed (${originalSize} -> ${html.length} bytes)`)
  if (fontFiles.length > 0) {
    console.log(`Post-build: injected ${fontFiles.length} font preload(s): ${fontFiles.join(", ")}`)
  }
  if (mirrorPath) {
    console.log(`Post-build: mirrored to ${mirrorPath} for static-serve compat`)
  }
  if (isLHCI) {
    console.log("Post-build: VITE_LHCI=true placeholders + visibility CSS applied")
  }
}

main()
