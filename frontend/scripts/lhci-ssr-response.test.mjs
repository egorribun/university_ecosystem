import assert from "node:assert/strict"
import test from "node:test"
import { gunzipSync } from "node:zlib"

import {
  isLhciSsrResponseMode,
  acceptsGzip,
  gzipResponse,
  prepareLhciSsrResponse,
  shouldCompressContentType,
  stripNonCriticalModulePreloads,
  stripLhciEntryScript,
} from "./lhci-ssr-response.mjs"

test("LHCI mode is explicit and case insensitive", () => {
  assert.equal(isLhciSsrResponseMode({ VITE_LHCI: "true", LHCI_USE_SSR_PREVIEW: "true" }), true)
  assert.equal(isLhciSsrResponseMode({ VITE_LHCI: "true", LHCI_USE_SSR_PREVIEW: "1" }), true)
  assert.equal(isLhciSsrResponseMode({ VITE_LHCI: "TRUE", LHCI_USE_SSR_PREVIEW: "TRUE" }), true)
  assert.equal(isLhciSsrResponseMode({ VITE_LHCI: "1" }), false)
  assert.equal(isLhciSsrResponseMode({ VITE_LHCI: "true" }), false)
  assert.equal(isLhciSsrResponseMode({}), false)
})

test("gzip negotiation honors explicit q=0 over wildcard", () => {
  assert.equal(acceptsGzip("gzip"), true)
  assert.equal(acceptsGzip("br, gzip;q=0.5"), true)
  assert.equal(acceptsGzip("gzip;q=0, *;q=1"), false)
  assert.equal(acceptsGzip("br, *;q=0.8"), true)
  assert.equal(acceptsGzip("br"), false)
  assert.equal(shouldCompressContentType("text/css; charset=utf-8"), true)
  assert.equal(shouldCompressContentType("image/png"), false)
})

test("keeps the application entry and strips speculative module preloads", () => {
  const html = [
    '<link rel="modulepreload" href="/assets/index-abc123.js">',
    '<link rel="modulepreload" href="/assets/vendor-react-def456.js">',
    '<link rel="stylesheet" href="/assets/index.css">',
  ].join("")

  const transformed = stripNonCriticalModulePreloads(html)
  assert.match(transformed, /index-abc123\.js/u)
  assert.doesNotMatch(transformed, /vendor-react-def456\.js/u)
  assert.match(transformed, /rel="stylesheet"/u)
})

test("strips only the hashed local application entry from the audit response", () => {
  const html = [
    '<script type="module" async src="/assets/index-abc123.js"></script>',
    '<script type="module" src="/assets/index-def456.js"></script>',
    '<script type="module" src="https://example.test/remote.js"></script>',
  ].join("")

  const transformed = stripLhciEntryScript(html)
  assert.doesNotMatch(transformed, /index-abc123\.js/u)
  assert.doesNotMatch(transformed, /index-def456\.js/u)
  assert.match(transformed, /https:\/\/example\.test\/remote\.js/u)
})

test("only buffers and rewrites HTML responses in explicit LHCI mode", async () => {
  const body = '<html><head><link rel="modulepreload" href="/assets/vendor-react.js"></head></html>'
  const source = new Response(body, {
    headers: {
      "content-type": "text/html; charset=utf-8",
      "content-length": "91",
    },
  })
  const unchanged = await prepareLhciSsrResponse(source, { enabled: false })
  assert.equal(unchanged, source)
  assert.equal(await unchanged.text(), body)
})

test("rewritten HTML drops stale content length and preserves response metadata", async () => {
  const response = new Response(
    '<html><head><link rel="modulepreload" href="/assets/index-abc.js"><link rel="modulepreload" href="/assets/map.js"></head><body><script type="module" async src="/assets/index-abc.js"></script></body></html>',
    {
      status: 201,
      statusText: "Created",
      headers: {
        "content-type": "text/html; charset=utf-8",
        "content-length": "130",
        "x-test": "preserved",
      },
    }
  )
  const transformed = await prepareLhciSsrResponse(response, { enabled: true })
  assert.equal(transformed.status, 201)
  assert.equal(transformed.statusText, "Created")
  assert.equal(transformed.headers.get("x-test"), "preserved")
  assert.equal(transformed.headers.get("content-length"), null)
  const body = await transformed.text()
  assert.match(body, /index-abc\.js/u)
  assert.doesNotMatch(body, /map\.js/u)
  assert.doesNotMatch(body, /window\.addEventListener\("load"/u)
  assert.doesNotMatch(body, /<script[^>]+src="\/assets\/index-abc\.js"/u)
})

test("HTML without module preloads still preserves response metadata", async () => {
  const response = new Response("<html><body>ready</body></html>", {
    status: 202,
    statusText: "Accepted",
    headers: {
      "content-type": "text/html; charset=utf-8",
      "content-length": "28",
      etag: '"stale"',
      "x-test": "preserved",
    },
  })
  const result = await prepareLhciSsrResponse(response, { enabled: true })
  assert.equal(result.status, 202)
  assert.equal(result.statusText, "Accepted")
  assert.equal(result.headers.get("x-test"), "preserved")
  assert.equal(result.headers.get("content-length"), null)
  assert.equal(result.headers.get("etag"), null)
  assert.equal(await result.text(), "<html><body>ready</body></html>")
})

test("non-HTML responses remain untouched", async () => {
  const response = new Response("binary", {
    headers: { "content-type": "application/octet-stream" },
  })
  const result = await prepareLhciSsrResponse(response, { enabled: true })
  assert.equal(await result.text(), "binary")
})

test("gzipResponse returns a valid encoded representation and varies correctly", async () => {
  const response = new Response("hello compressed world", {
    headers: {
      "content-type": "text/html; charset=utf-8",
      etag: '"identity"',
      vary: "Origin",
    },
  })
  const result = await gzipResponse(response, { acceptEncoding: "br, gzip", enabled: true })
  assert.equal(result.headers.get("content-encoding"), "gzip")
  assert.equal(result.headers.get("vary"), "Origin, Accept-Encoding")
  assert.equal(result.headers.get("etag"), null)
  assert.equal(result.headers.get("content-length"), null)
  assert.equal(
    gunzipSync(Buffer.from(await result.arrayBuffer())).toString(),
    "hello compressed world"
  )
})

test("gzipResponse leaves unsupported or unadvertised responses unchanged", async () => {
  const image = new Response("png", { headers: { "content-type": "image/png" } })
  const unsupported = await gzipResponse(image, { acceptEncoding: "gzip", enabled: true })
  assert.equal(unsupported.headers.get("content-encoding"), null)
  assert.equal(await unsupported.text(), "png")

  const html = new Response("html", { headers: { "content-type": "text/html" } })
  const notAdvertised = await gzipResponse(html, { acceptEncoding: "br", enabled: true })
  assert.equal(notAdvertised.headers.get("content-encoding"), null)
  assert.equal(await notAdvertised.text(), "html")

  const production = new Response("html", { headers: { "content-type": "text/html" } })
  const unbuffered = await gzipResponse(production, { acceptEncoding: "gzip", enabled: false })
  assert.equal(unbuffered, production)
})
