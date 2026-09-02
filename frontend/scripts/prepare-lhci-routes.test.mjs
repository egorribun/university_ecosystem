import assert from "node:assert/strict"
import test from "node:test"

import { prepareLhciHtml, routeSourcePath } from "./prepare-lhci-routes.mjs"

test("LHCI preparation adds the mode class after post-build html attributes", () => {
  const html =
    '<!doctype html><html data-render-mode="static-spa" lang="ru"><head></head><body></body></html>'

  const prepared = prepareLhciHtml(html)

  assert.match(prepared, /<html data-render-mode="static-spa" lang="ru" class="lhci-mode">/u)
  assert.match(prepared, /\.lhci-mode \.aurora-mesh::after/u)
  assert.match(prepared, /\.lhci-mode \.skeleton\s*\{/u)
  assert.match(prepared, /\.lhci-mode \.skeleton::after/u)
  assert.match(prepared, /animation:\s*none\s*!important/u)
})

test("LHCI preparation preserves existing classes and stays idempotent", () => {
  const html = '<html class="dark" data-render-mode="static-spa"><head></head><body></body></html>'

  const once = prepareLhciHtml(html)
  const twice = prepareLhciHtml(once)

  assert.match(once, /<html class="dark lhci-mode" data-render-mode="static-spa">/u)
  assert.equal(
    (twice.match(/<html class="dark lhci-mode" data-render-mode="static-spa">/gu) ?? []).length,
    1
  )
  assert.equal((twice.match(/<style data-lhci-static-effects>/gu) ?? []).length, 1)
})

test("LHCI preparation removes the legacy marker without injecting executable HTML", () => {
  const html = '<html lang="en"><head><!-- LHCI_MODE_MARKER --></head><body></body></html>'

  const prepared = prepareLhciHtml(html)

  assert.doesNotMatch(prepared, /LHCI_MODE_MARKER/u)
  assert.match(prepared, /<html lang="en" class="lhci-mode">/u)
  assert.doesNotMatch(prepared, /<script/iu)
})

test("LHCI preparation does not promote the diagnostic marker into an LCP candidate", () => {
  const html =
    '<html lang="ru"><head></head><body><div id="lhci-marker" style="display: none">LHCI RENDER START</div></body></html>'

  const prepared = prepareLhciHtml(html)

  assert.match(prepared, /id="lhci-marker"[^>]*display: none/u)
  assert.doesNotMatch(prepared, /LHCI RENDER START[^<]*<\/div>[^]*display:\s*flex/u)
})

test("the unknown-document audit uses the dedicated lightweight fallback", () => {
  const entryPath = "dist/client/index.html"
  const notFoundPath = "dist/client/not-found.html"

  assert.equal(routeSourcePath("404", entryPath, notFoundPath), notFoundPath)
  assert.equal(routeSourcePath("dashboard", entryPath, notFoundPath), entryPath)
})
