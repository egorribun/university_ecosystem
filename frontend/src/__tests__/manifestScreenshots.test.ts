/**
 * @vitest-environment node
 *
 * Wave 175 SW9 — regression test for W174 SW3 PWA manifest screenshots
 * removal.
 *
 * W174 SW3 deleted the `screenshots` array from
 * `frontend/public/manifest.source.json` after empirical verification
 * via chrome-devtools-mcp that the production frontend served the
 * manifest with `screenshots: [{"src": "/screenshots/schedule-wide.png",
 * ...}, {"src": "/screenshots/schedule-narrow.png", ...}]` but the
 * `screenshots/` directory contained only `.gitkeep` — orphan
 * declarations producing real-user 404s in DevTools + browser manifest
 * download warnings.
 *
 * The canonical source-of-truth is `manifest.source.json`;
 * `manifest.webmanifest` + `manifest.<locale>.webmanifest` are
 * generated via `frontend/scripts/generate-manifests.mjs --check`
 * which fails CI if any drift between source + generated outputs.
 *
 * This test guards against re-introduction by reading the SOURCE JSON
 * + ALL generated locale variants + asserting no `screenshots` key.
 *
 * Closes W174 §Honesty #5 ("no automated regression test added for the
 * manifest screenshots removal — fix verified empirically via
 * chrome-devtools-mcp + curl + manifest.webmanifest grep").
 */
import { readFileSync } from "node:fs"
import { resolve, dirname } from "node:path"
import { fileURLToPath } from "node:url"

import { describe, expect, it } from "vitest"

const __dirname = dirname(fileURLToPath(import.meta.url))
// __dirname is frontend/src/__tests__ → climb 2 levels to reach frontend/
const FRONTEND_DIR = resolve(__dirname, "../..")
const PUBLIC_DIR = resolve(FRONTEND_DIR, "public")

// Only 3 manifest files actually exist; default `manifest.webmanifest`
// is the Russian locale (per generate-manifests.mjs default).
const MANIFEST_FILES = ["manifest.source.json", "manifest.webmanifest", "manifest.en.webmanifest"]

describe("W174 SW3 — PWA manifest screenshots removal regression guard", () => {
  it.each(MANIFEST_FILES)("%s does NOT contain screenshots key", (filename) => {
    const path = resolve(PUBLIC_DIR, filename)
    const raw = readFileSync(path, "utf-8")
    const manifest = JSON.parse(raw) as Record<string, unknown>

    // Critical invariant: screenshots key MUST NOT be present
    expect(manifest).not.toHaveProperty("screenshots")
  })

  it("manifest.source.json is valid JSON (parse without throwing)", () => {
    const sourcePath = resolve(PUBLIC_DIR, "manifest.source.json")
    expect(() => JSON.parse(readFileSync(sourcePath, "utf-8"))).not.toThrow()
  })

  it("generated manifests have required PWA fields", () => {
    // Default generated manifest (Russian locale per generate-manifests.mjs)
    const defaultGen = JSON.parse(
      readFileSync(resolve(PUBLIC_DIR, "manifest.webmanifest"), "utf-8")
    ) as Record<string, unknown>

    // Critical PWA fields that MUST exist (generate-manifests.mjs --check
    // fails CI on drift from source; this is a defense-in-depth assertion
    // that the GENERATED manifest is a valid PWA manifest, not just empty).
    for (const field of ["start_url", "scope", "display", "icons"] as const) {
      expect(defaultGen[field]).toBeDefined()
    }
    expect(Array.isArray(defaultGen.icons)).toBe(true)
    expect((defaultGen.icons as unknown[]).length).toBeGreaterThan(0)

    // source.json uses different shape (nested `base.{...}` config) — only
    // verify screenshots absence (the W174 SW3 invariant), not field shape.
  })
})
