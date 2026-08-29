import test from "node:test"
import assert from "node:assert/strict"

import {
  pathForLhciPreview,
  previewReadyPattern,
  previewServerCommand,
  resolveLhciPreviewMode,
} from "./lhci-preview-mode.mjs"

test("defaults to static fallback mode when no preview is requested", () => {
  const mode = resolveLhciPreviewMode({})

  assert.deepEqual(mode, { kind: "static", base: "" })
  assert.equal(previewServerCommand(mode), null)
  assert.equal(previewReadyPattern(mode), null)
})

test("selects the production SSR wrapper for CI route measurements", () => {
  const mode = resolveLhciPreviewMode({ LHCI_USE_SSR_PREVIEW: "1" })

  assert.deepEqual(mode, { kind: "ssr", base: "http://127.0.0.1:4175", port: 4175 })
  assert.equal(previewServerCommand(mode), "node scripts/server-prod.mjs")
  assert.equal(previewReadyPattern(mode), "server-prod: listening")
})

test("accepts the textual SSR flag and gives remote previews precedence", () => {
  const textual = resolveLhciPreviewMode({ LHCI_USE_SSR_PREVIEW: "TRUE" })
  assert.deepEqual(textual, { kind: "ssr", base: "http://127.0.0.1:4175", port: 4175 })

  const customPort = resolveLhciPreviewMode({
    LHCI_USE_SSR_PREVIEW: "1",
    LHCI_SSR_PREVIEW_PORT: "4317",
  })
  assert.deepEqual(customPort, { kind: "ssr", base: "http://127.0.0.1:4317", port: 4317 })

  const remote = resolveLhciPreviewMode({
    LHCI_USE_SSR_PREVIEW: "1",
    PREVIEW_URL: "https://preview.example.test",
  })
  assert.deepEqual(remote, { kind: "remote", base: "https://preview.example.test" })
  assert.equal(previewServerCommand(remote), "node scripts/lhci-preview.mjs")
  assert.equal(previewReadyPattern(remote), "LHCI_READY")
})

test("falls back to the managed SSR port for invalid input", () => {
  const invalidPort = resolveLhciPreviewMode({
    LHCI_USE_SSR_PREVIEW: "true",
    LHCI_SSR_PREVIEW_PORT: "not-a-port",
  })

  assert.deepEqual(invalidPort, {
    kind: "ssr",
    base: "http://127.0.0.1:4175",
    port: 4175,
  })
})

test("SSR preview addresses canonical paths without redirecting Lighthouse", () => {
  const ssr = { kind: "ssr" }
  assert.equal(pathForLhciPreview("/dashboard/", ssr), "/dashboard")
  assert.equal(pathForLhciPreview("/events", ssr), "/events")
  assert.equal(pathForLhciPreview("/", ssr), "/")
  assert.equal(pathForLhciPreview("/dashboard/", { kind: "static" }), "/dashboard/")
})
