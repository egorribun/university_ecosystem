import assert from "node:assert/strict"
import test from "node:test"

import { prepareLhciHtml } from "./prepare-lhci-routes.mjs"

test("LHCI preparation adds the mode class after post-build html attributes", () => {
  const html =
    '<!doctype html><html data-render-mode="static-spa" lang="ru"><head></head><body></body></html>'

  const prepared = prepareLhciHtml(html)

  assert.match(prepared, /<html data-render-mode="static-spa" lang="ru" class="lhci-mode">/u)
  assert.match(prepared, /\.lhci-mode \.aurora-mesh::after/u)
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
