import assert from "node:assert/strict"
import { generateKeyPairSync, verify } from "node:crypto"
import test from "node:test"
import { proveSsrAuthentication } from "./ssr_mtls_request_proof.mjs"
import { applyNodeCspToHtmlResponse } from "../../frontend/scripts/server-csp.mjs"

const { privateKey, publicKey } = generateKeyPairSync("rsa", { modulusLength: 2048 })
const key = { ...publicKey.export({ format: "jwk" }), kid: "proof" }
const config = {
  privateKey,
  issuer: "proof-issuer",
  port: "3000",
  backendOrigin: "http://127.0.0.1:18000",
}

function fixture(change = {}) {
  let calls = 0
  const request = async (url, options) => {
    calls += 1
    assert.equal(options.redirect, "manual")
    assert.ok(options.signal instanceof AbortSignal)
    if (calls === 1) {
      assert.equal(url, config.backendOrigin + "/.well-known/jwks.json")
      return Response.json({ keys: change.keys ?? [key] }, { status: change.jwksStatus ?? 200 })
    }
    if (calls === 2) {
      assert.equal(url, config.backendOrigin + "/api/v1/users/me")
      assert.deepEqual(options.headers, {})
      return new Response("", { status: change.userStatus ?? 401 })
    }
    assert.equal(
      url,
      calls === 5
        ? "http://127.0.0.1:3000/dashboard"
        : "http://127.0.0.1:3000/login?redirect=%2Fdashboard"
    )
    const parts = options.headers.cookie.slice("access_token_v2=".length).split(".")
    const valid = verify(
      "RSA-SHA256",
      Buffer.from(parts.slice(0, 2).join(".")),
      publicKey,
      Buffer.from(parts[2], "base64url")
    )
    assert.equal(valid, calls === 3)
    const claims = JSON.parse(Buffer.from(parts[1], "base64url").toString())
    assert.equal(claims.iss, config.issuer)
    assert.equal(claims.aud, "university-ecosystem-api")
    if (calls === 3) {
      return new Response("", {
        status: change.acceptedStatus ?? 307,
        headers: {
          location: change.location ?? "/dashboard",
          "cache-control": change.acceptedCache ?? "no-store, private, max-age=0",
        },
      })
    }
    if (calls === 5) {
      return new Response("", {
        status: change.protectedStatus ?? 307,
        headers: { location: change.protectedLocation ?? "/login?redirect=%2Fdashboard" },
      })
    }
    assert.equal(calls, 4)
    const response = new Response(change.body ?? "<html><body>login</body></html>", {
      status: change.rejectedStatus ?? 200,
      headers: {
        "cache-control": change.rejectedCache ?? "no-store, private, max-age=0",
        "content-type": change.contentType ?? "text/html; charset=utf-8",
        ...(change.forgedLocation ? { location: change.forgedLocation } : {}),
      },
    })
    return change.productionCsp
      ? applyNodeCspToHtmlResponse(response, "proof-nonce")
      : response
  }
  return { request, calls: () => calls }
}

test("real signed and forged tokens require independent SSR outcomes", async () => {
  const control = fixture()
  await proveSsrAuthentication({ ...config, request: control.request })
  assert.equal(control.calls(), 5)
})

test("accepts the real CSP policy on unauthenticated HTML without treating privacy as auth", async () => {
  const control = fixture({ productionCsp: true, rejectedCache: "public, max-age=600" })
  await proveSsrAuthentication({ ...config, request: control.request })
  assert.equal(control.calls(), 5)
})

for (const [name, change] of Object.entries({
  jwks: { jwksStatus: 503 },
  key: { keys: [] },
  authBypass: { userStatus: 200 },
  noRedirect: { acceptedStatus: 200 },
  wrongRedirect: { location: "/login" },
  missingPrivacy: { acceptedCache: "public" },
  forgedAccepted: { rejectedStatus: 307 },
  forgedPublic: { rejectedCache: "public, max-age=600" },
  forgedMissingNoStore: { rejectedCache: "private" },
  forgedRedirectHeader: { forgedLocation: "/dashboard" },
  forgedNonHtmlType: { contentType: "application/json" },
  missingHtml: { body: "not a document" },
  protectedContent: { protectedStatus: 200 },
  protectedWrongRedirect: { protectedLocation: "/dashboard" },
})) {
  test("rejects incomplete proof: " + name, async () => {
    await assert.rejects(proveSsrAuthentication({ ...config, request: fixture(change).request }))
  })
}

for (const change of [
  { backendOrigin: "http://backend:8000" },
  { port: "0" },
  { port: "65536" },
  { issuer: "" },
]) {
  test("rejects invalid runtime configuration " + JSON.stringify(change), async () => {
    await assert.rejects(
      proveSsrAuthentication({ ...config, ...change, request: fixture().request })
    )
  })
}

test("network failure cannot become a successful receipt", async () => {
  await assert.rejects(
    proveSsrAuthentication({
      ...config,
      request: async () => {
        throw new Error("offline")
      },
    })
  )
})

test("failed user authentication reports its finite boundary without payloads", async () => {
  const stages = []
  await assert.rejects(
    proveSsrAuthentication({
      ...config,
      request: fixture({ userStatus: 403 }).request,
      onStage: (stage) => stages.push(stage),
    })
  )
  assert.deepEqual(stages, [
    "configuration", "jwks-request", "jwks-status", "jwks-key",
    "user-request", "user-status",
  ])
})

test("forged response failure cannot be attributed to successful signed authentication", async () => {
  const stages = []
  await assert.rejects(
    proveSsrAuthentication({
      ...config,
      request: fixture({ rejectedStatus: 307 }).request,
      onStage: (stage) => stages.push(stage),
    })
  )
  assert.equal(stages.at(-1), "forged-status")
  assert.ok(stages.includes("signed-cache"))
})
