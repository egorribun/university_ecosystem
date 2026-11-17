import assert from "node:assert/strict"
import { generateKeyPairSync, verify } from "node:crypto"
import test from "node:test"
import { proveSsrAuthentication } from "./ssr_mtls_request_proof.mjs"

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
    assert.equal(url, "http://127.0.0.1:3000/login?redirect=%2Fdashboard")
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
    assert.equal(calls, 4)
    return new Response(change.body ?? "<html><body>login</body></html>", {
      status: change.rejectedStatus ?? 200,
      headers: { "cache-control": change.rejectedCache ?? "no-store" },
    })
  }
  return { request, calls: () => calls }
}

test("real signed and forged tokens require independent SSR outcomes", async () => {
  const control = fixture()
  await proveSsrAuthentication({ ...config, request: control.request })
  assert.equal(control.calls(), 4)
})

for (const [name, change] of Object.entries({
  jwks: { jwksStatus: 503 },
  key: { keys: [] },
  authBypass: { userStatus: 200 },
  noRedirect: { acceptedStatus: 200 },
  wrongRedirect: { location: "/login" },
  missingPrivacy: { acceptedCache: "public" },
  forgedAccepted: { rejectedStatus: 307 },
  forgedPrivate: { rejectedCache: "private" },
  missingHtml: { body: "not a document" },
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
