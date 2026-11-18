// Executed inside the real frontend container. The isolated proof key arrives
// only on stdin; receipts contain neither keys, tokens, cookies nor responses.
import assert from "node:assert/strict"
import { createPublicKey, sign } from "node:crypto"
import { readFileSync } from "node:fs"

export async function proveSsrAuthentication({
  privateKey,
  issuer,
  port,
  backendOrigin,
  request = fetch,
  onStage = () => {},
}) {
  onStage("configuration")
  assert.equal(backendOrigin, "http://127.0.0.1:18000")
  assert.match(String(port), /^[1-9][0-9]{0,4}$/u)
  assert.ok(Number(port) <= 65535)
  assert.ok(issuer)
  const localOrigin = `http://127.0.0.1:${port}`
  const get = (url, cookie) =>
    request(url, {
      redirect: "manual",
      signal: AbortSignal.timeout(15000),
      headers: cookie ? { cookie } : {},
    })
  onStage("jwks-request")
  const jwksResponse = await get(`${backendOrigin}/.well-known/jwks.json`)
  onStage("jwks-status")
  assert.equal(jwksResponse.status, 200)
  onStage("jwks-key")
  const jwks = await jwksResponse.json()
  const publicKey = createPublicKey(privateKey).export({ format: "jwk" })
  const key = jwks.keys.find((item) => item.n === publicKey.n && item.e === publicKey.e)
  assert.ok(key?.kid)
  // Workload authentication must not bypass user authentication.
  onStage("user-request")
  const userResponse = await get(`${backendOrigin}/api/v1/users/me`)
  onStage("user-status")
  assert.equal(userResponse.status, 401)
  await userResponse.arrayBuffer()
  onStage("signing")
  const encode = (value) => Buffer.from(JSON.stringify(value)).toString("base64url")
  const unsigned = `${encode({ alg: "RS256", typ: "JWT", kid: key.kid })}.${encode({
    iss: issuer,
    aud: "university-ecosystem-api",
    sub: "00000000-0000-4000-8000-000000000001",
    role: "student",
    exp: Math.floor(Date.now() / 1000) + 120,
  })}`
  const signature = sign("RSA-SHA256", Buffer.from(unsigned), privateKey)
  const token = `${unsigned}.${signature.toString("base64url")}`
  const login = `${localOrigin}/login?redirect=%2Fdashboard`
  onStage("signed-request")
  const accepted = await get(login, `access_token_v2=${token}`)
  onStage("signed-status")
  assert.ok([301, 302, 303, 307, 308].includes(accepted.status))
  onStage("signed-location")
  const acceptedLocation = new URL(accepted.headers.get("location"), localOrigin)
  assert.equal(acceptedLocation.origin, localOrigin)
  assert.equal(acceptedLocation.pathname, "/dashboard")
  onStage("signed-cache")
  assert.match(accepted.headers.get("cache-control") ?? "", /private/u)
  await accepted.arrayBuffer()
  signature[0] ^= 1
  const forged = `${unsigned}.${signature.toString("base64url")}`
  onStage("forged-request")
  const rejected = await get(login, `access_token_v2=${forged}`)
  onStage("forged-status")
  assert.equal(rejected.status, 200)
  onStage("forged-cache")
  // A per-request CSP nonce makes every HTML document private, including login.
  // Authentication is proved by signed redirect versus forged 200, not cacheability.
  assert.equal(rejected.headers.get("cache-control"), "no-store, private, max-age=0")
  onStage("forged-location")
  assert.equal(rejected.headers.get("location"), null)
  onStage("forged-content-type")
  assert.match(rejected.headers.get("content-type") ?? "", /^text\/html(?:;|$)/iu)
  onStage("forged-html")
  assert.match(await rejected.text(), /<html[\s>]/iu)
  onStage("protected-request")
  const protectedResponse = await get(`${localOrigin}/dashboard`, `access_token_v2=${forged}`)
  onStage("protected-status")
  assert.ok([301, 302, 303, 307, 308].includes(protectedResponse.status))
  onStage("protected-location")
  const protectedLocation = new URL(protectedResponse.headers.get("location"), localOrigin)
  assert.equal(protectedLocation.origin, localOrigin)
  assert.equal(protectedLocation.pathname, "/login")
  await protectedResponse.arrayBuffer()
}

if (process.argv.includes("--run")) {
  let stage = "configuration"
  try {
    await proveSsrAuthentication({
      onStage: (value) => {
        stage = value
      },
      privateKey: readFileSync(0, "utf8"),
      issuer: process.env.JWT_ISSUER,
      port: process.env.PORT,
      backendOrigin: process.env.BACKEND_ORIGIN,
    })
    console.log("SSR_MTLS_AUTH=PASS")
  } catch {
    console.log(`SSR_MTLS_AUTH=FAIL stage=${stage}`)
    process.exitCode = 1
  }
}
