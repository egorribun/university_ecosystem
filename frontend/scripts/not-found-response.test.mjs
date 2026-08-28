import assert from "node:assert/strict"
import test from "node:test"

import { createNotFoundResponse, shouldServeNotFoundDocument } from "./not-found-response.mjs"

test("document requests are eligible for the product 404 page", () => {
  assert.equal(
    shouldServeNotFoundDocument({ method: "GET", urlPath: "/missing", accept: "text/html" }),
    true
  )
  assert.equal(
    shouldServeNotFoundDocument({ method: "HEAD", urlPath: "/missing", accept: "*/*" }),
    true
  )
  assert.equal(
    shouldServeNotFoundDocument({ method: "GET", urlPath: "/404", accept: "text/html" }),
    true
  )
})

test("non-document requests keep their original API or asset 404 response", () => {
  assert.equal(
    shouldServeNotFoundDocument({ method: "POST", urlPath: "/missing", accept: "text/html" }),
    false
  )
  assert.equal(
    shouldServeNotFoundDocument({ method: "GET", urlPath: "/missing.js", accept: "*/*" }),
    false
  )
  assert.equal(
    shouldServeNotFoundDocument({
      method: "GET",
      urlPath: "/api/missing",
      accept: "application/json",
    }),
    false
  )
  assert.equal(
    shouldServeNotFoundDocument({ method: "GET", urlPath: "/graphql", accept: "*/*" }),
    false
  )
  assert.equal(
    shouldServeNotFoundDocument({ method: "GET", urlPath: "/graphql/query", accept: "text/html" }),
    false
  )
})

test("the 404 response has safe cache and content headers", async () => {
  const response = createNotFoundResponse("<h1>Not found</h1>")

  assert.equal(response.status, 404)
  assert.equal(response.headers.get("content-type"), "text/html; charset=utf-8")
  assert.equal(response.headers.get("cache-control"), "no-store, max-age=0")
  assert.equal(response.headers.get("x-content-type-options"), "nosniff")
  assert.equal(response.headers.get("x-robots-tag"), "noindex, nofollow")
  assert.equal(await response.text(), "<h1>Not found</h1>")
})

test("HEAD 404 responses carry headers without a response body", async () => {
  const response = createNotFoundResponse("<h1>Not found</h1>", { method: "HEAD" })

  assert.equal(response.status, 404)
  assert.equal(response.body, null)
  assert.equal(await response.text(), "")
})
