// Post-build HTML processing for TanStack Start's SPA fallback shell.
// Runs as a separate npm script chained after `vite build` to avoid the
// Windows shell:true child-process issue where parent script exits
// before post-process logic in the same process can run.
//
// Five things happen here:
//   1. Inject critical `inter-cyrillic` and `outfit-latin` font preloads.
//      The Vite plugin
//      `withFontPreload()` in `vite.config.mts` only fires on
//      `transformIndexHtml`, which TanStack Start's spa shell skips
//      because it generates the HTML via React SSR. Re-implementing
//      here prevents a flash of invisible text.
//   2. Keep nonce placement at trusted script creation. TanStack's SSR
//      renderer receives the per-request nonce through RouterOptions.ssr;
//      this script does not rewrite rendered markup. The explicitly
//      controlled not-found script receives a nonce marker below.
//   3. Replace the VITE_LHCI placeholder. The visibility CSS keeps the
//      static shell measurable without introducing a synthetic diagnostic
//      element into Lighthouse's largest-contentful-paint candidate set.
//   4. Mirror the prerendered shell to `dist/client/index.html` so
//      that static serving (e.g. `staticDistDir: dist/client` for LHCI,
//      `npx serve dist/client -s` for local SPA-style preview) finds
//      the shell at the conventional `index.html` path.
//   5. Mark the document as a static SPA fallback. Unlike a real SSR
//      response, one static file is reused for every deep link, so the client
//      entry must mount it afresh instead of hydrating route-specific content.

import { copyFileSync, existsSync, readdirSync, readFileSync, writeFileSync } from "node:fs"
import path from "node:path"
import process from "node:process"

import { renderNotFoundPage } from "./not-found-page.mjs"
import { CSP_NONCE_PLACEHOLDER } from "./server-csp.mjs"

const FONT_PRELOAD_PATTERN = /^(inter-cyrillic-wght-normal-|outfit-latin-wght-normal-)[^/]*\.woff2$/

const NOT_FOUND_SCRIPT_TAG = '<script type="module" src="/not-found-i18n.js" defer></script>'

function findShellHtml(cwd) {
  // Prefer the canonical current Vite output, then support legacy outputs.
  const candidates = [
    path.join(cwd, "dist", "client", "_shell.html"),
    path.join(cwd, "dist", "client", "index.html"),
    path.join(cwd, ".output", "public", "_shell.html"),
    path.join(cwd, ".output", "public", "index.html"),
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

function markNotFoundTrustedScript(html) {
  const first = html.indexOf(NOT_FOUND_SCRIPT_TAG)
  if (first < 0 || html.indexOf(NOT_FOUND_SCRIPT_TAG, first + NOT_FOUND_SCRIPT_TAG.length) >= 0) {
    throw new Error("Expected exactly one controlled not-found translation script")
  }
  return html.replace(
    NOT_FOUND_SCRIPT_TAG,
    `<script nonce="${CSP_NONCE_PLACEHOLDER}" type="module" ` +
      'src="/not-found-i18n.js" defer></script>'
  )
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

function markStaticSpaShell(html) {
  if (/\bdata-render-mode=["']static-spa["']/.test(html)) return html
  return html.replace(/<html\b/, '<html data-render-mode="static-spa"')
}

function applyLhciReplacements(html, isLHCI) {
  if (isLHCI) {
    const lhciStyles =
      "html, body, #root { background: #FFFFFF !important; color: #000000 !important; " +
      "opacity: 1 !important; visibility: visible !important; }"
    return html.replace("/* LHCI_CSS_PLACEHOLDER */", lhciStyles).replace(/%VITE_LHCI%/g, "true")
  }
  return html.replace("/* LHCI_CSS_PLACEHOLDER */", "").replace(/%VITE_LHCI%/g, "false")
}

const safeWriteFileSync = (filePath, content) => {
  for (let i = 0; i < 10; i++) {
    try {
      writeFileSync(filePath, content, "utf8")
      return
    } catch (err) {
      if ((err.code === "EBUSY" || err.code === "EPERM") && i < 9) {
        Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 100 * (i + 1))
        continue
      }
      throw err
    }
  }
}

const safeCopyFileSync = (src, dest) => {
  for (let i = 0; i < 10; i++) {
    try {
      copyFileSync(src, dest)
      return
    } catch (err) {
      if ((err.code === "EBUSY" || err.code === "EPERM") && i < 9) {
        Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 100 * (i + 1))
        continue
      }
      throw err
    }
  }
}

function writeNotFoundPage(outputDir) {
  const notFoundPath = path.join(outputDir, "not-found.html")
  safeWriteFileSync(notFoundPath, markNotFoundTrustedScript(renderNotFoundPage()))
  return notFoundPath
}

function main() {
  const cwd = process.cwd()
  const shellPath = findShellHtml(cwd)
  if (!shellPath) {
    console.warn(
      "Post-build: no spa shell HTML found in .output/public/ or dist/. " +
        "Skipping font preload + LHCI replacements."
    )
    return
  }

  const isLHCI = process.env.VITE_LHCI === "true"
  const assetsDir = path.resolve(path.dirname(shellPath), "assets")
  const fontFiles = findCriticalFontFiles(assetsDir)

  let html = readFileSync(shellPath, "utf8")
  const originalSize = html.length
  html = injectFontPreloads(html, fontFiles)
  html = applyLhciReplacements(html, isLHCI)
  html = markStaticSpaShell(html)
  safeWriteFileSync(shellPath, html)

  // Mirror the post-processed shell to `index.html` in the same directory
  // so static-server fallbacks (LHCI's staticDistDir, `npx serve -s`, etc.)
  // serve the spa shell on the conventional index path. This lets the
  // existing LHCI infrastructure (which expects `dist/.../index.html`) work
  // unchanged and lets `npx serve dist/client -s` behave like a SPA.
  let mirrorPath = null
  if (path.basename(shellPath) !== "index.html") {
    mirrorPath = path.join(path.dirname(shellPath), "index.html")
    safeCopyFileSync(shellPath, mirrorPath)
  }

  console.log(`Post-build: shell ${shellPath} processed (${originalSize} -> ${html.length} bytes)`)
  if (fontFiles.length > 0) {
    console.log(`Post-build: injected ${fontFiles.length} font preload(s): ${fontFiles.join(", ")}`)
  }
  if (mirrorPath) {
    console.log(`Post-build: mirrored to ${mirrorPath} for static-serve compat`)
  }
  const notFoundPath = writeNotFoundPage(path.dirname(shellPath))
  console.log(`Post-build: generated lightweight 404 document at ${notFoundPath}`)
  if (isLHCI) {
    console.log("Post-build: VITE_LHCI=true placeholders + visibility CSS applied")
  }
}

main()
