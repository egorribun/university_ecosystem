// @vitest-environment node
import { readFile } from "node:fs/promises"
import { createServer } from "node:http"
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from "vitest"
import { exportJWK, generateKeyPair, jwtVerify, SignJWT } from "jose"
import { parseAllDocuments } from "yaml"

const expectedIssuer = "https://issuer.example.test"
const audience = "university-ecosystem-api"
type SigningKeyPair = {
  kid: string
  privateKey: CryptoKey
  publicKey: CryptoKey
}

let previousKey: SigningKeyPair
let activeKey: SigningKeyPair
let jwksServer: ReturnType<typeof createServer>
let validateJwt: typeof import("../ssrAuth").validateJwt
let SSR_AUTH_UNAUTH: typeof import("../ssrAuth").SSR_AUTH_UNAUTH
let setJwtVerifyOverrideForTests: typeof import("../ssrAuth")._setJwtVerifyOverrideForTests

type K8sContainer = {
  name?: string
  envFrom?: Array<{ configMapRef?: { name?: string; optional?: boolean } }>
  env?: Array<{
    name?: string
    valueFrom?: {
      configMapKeyRef?: { name?: string; key?: string; optional?: boolean }
    }
  }>
}

type K8sDocument = {
  kind?: string
  metadata?: { name?: string; namespace?: string }
  data?: Record<string, string>
  spec?: {
    template?: {
      spec?: { containers?: K8sContainer[] }
    }
  }
}

async function readK8sDocuments(relativePath: string): Promise<K8sDocument[]> {
  const relativeDocumentPath = `../../../${relativePath}`
  const source = await readFile(new URL(relativeDocumentPath, import.meta.url), "utf8")
  const documents = parseAllDocuments(source)
  expect(documents.every((document) => document.errors.length === 0)).toBe(true)
  return documents.map((document) => document.toJSON() as K8sDocument)
}

async function signedToken(
  issuer?: string,
  signingKey: SigningKeyPair = activeKey
): Promise<string> {
  const jwt = new SignJWT({ role: "admin" })
    .setProtectedHeader({ alg: "RS256", kid: signingKey.kid })
    .setSubject("ssr-issuer-test-user")
    .setAudience(audience)
    .setIssuedAt()
    .setExpirationTime("2m")
  if (issuer !== undefined) jwt.setIssuer(issuer)
  return jwt.sign(signingKey.privateKey)
}

describe("ssrAuth issuer validation with real jose and local JWKS", () => {
  beforeAll(async () => {
    vi.stubEnv("NODE_ENV", "development")
    vi.stubEnv("JWT_ISSUER", expectedIssuer)
    const previousKeys = await generateKeyPair("RS256")
    const activeKeys = await generateKeyPair("RS256")
    previousKey = { ...previousKeys, kid: "ssr-previous-key" }
    activeKey = { ...activeKeys, kid: "ssr-active-key" }
    const publicJwks = await Promise.all(
      [previousKey, activeKey].map(async (key) => {
        const publicJwk = await exportJWK(key.publicKey)
        return Object.assign(publicJwk, { alg: "RS256", kid: key.kid, use: "sig" })
      })
    )

    jwksServer = createServer((request, response) => {
      if (request.url !== "/.well-known/jwks.json") {
        response.writeHead(404).end()
        return
      }
      response
        .writeHead(200, { "content-type": "application/json", "cache-control": "no-store" })
        .end(JSON.stringify({ keys: publicJwks }))
    })
    await new Promise<void>((resolve, reject) => {
      jwksServer.once("error", reject)
      jwksServer.listen(0, "127.0.0.1", resolve)
    })
    const address = jwksServer.address()
    if (!address || typeof address === "string") throw new Error("local JWKS server did not bind")
    vi.stubEnv("BACKEND_ORIGIN", `http://127.0.0.1:${address.port}`)

    vi.resetModules()
    const ssrAuth = await import("../ssrAuth")
    validateJwt = ssrAuth.validateJwt
    SSR_AUTH_UNAUTH = ssrAuth.SSR_AUTH_UNAUTH
    setJwtVerifyOverrideForTests = ssrAuth._setJwtVerifyOverrideForTests
  })

  beforeEach(() => {
    setJwtVerifyOverrideForTests(null)
    vi.stubEnv("NODE_ENV", "development")
    vi.stubEnv("JWT_ISSUER", expectedIssuer)
  })

  afterAll(async () => {
    setJwtVerifyOverrideForTests(null)
    vi.unstubAllEnvs()
    if (jwksServer?.listening) {
      await new Promise<void>((resolve, reject) => {
        jwksServer.close((error) => (error ? reject(error) : resolve()))
      })
    }
  })

  it("shares the required backend-config issuer with the raw Kubernetes frontend", async () => {
    const [configMaps, backendManifests, frontendManifests] = await Promise.all([
      readK8sDocuments("k8s/backend/configmap.yaml"),
      readK8sDocuments("k8s/backend/deployment.yaml"),
      readK8sDocuments("k8s/frontend/deployment.yaml"),
    ])
    const configMap = configMaps.find((document) => document.kind === "ConfigMap")
    const backend = backendManifests.find((document) => document.kind === "Deployment")
    const frontend = frontendManifests.find((document) => document.kind === "Deployment")

    expect(configMap).toMatchObject({
      metadata: { name: "backend-config", namespace: "university-ecosystem" },
      data: { JWT_ISSUER: "university-ecosystem" },
    })
    expect(backend?.metadata?.namespace).toBe(configMap?.metadata?.namespace)
    const backendContainer = backend?.spec?.template?.spec?.containers?.find(
      (container) => container.name === "backend"
    )
    expect(backendContainer?.envFrom).toContainEqual({
      configMapRef: { name: "backend-config" },
    })
    const backendConfigRef = backendContainer?.envFrom?.find(
      (source) => source.configMapRef?.name === "backend-config"
    )?.configMapRef
    expect(backendConfigRef?.optional ?? false).toBe(false)

    expect(frontend?.metadata?.namespace).toBe(configMap?.metadata?.namespace)
    const frontendContainer = frontend?.spec?.template?.spec?.containers?.find(
      (container) => container.name === "frontend"
    )
    const issuerEnv = frontendContainer?.env?.find((entry) => entry.name === "JWT_ISSUER")
    expect(issuerEnv?.valueFrom?.configMapKeyRef).toEqual({
      name: "backend-config",
      key: "JWT_ISSUER",
      optional: false,
    })
  })

  it("real jose accepts a signed token with the right audience but no issuer, while SSR rejects it", async () => {
    const token = await signedToken()
    const verified = await jwtVerify(token, activeKey.publicKey, { audience })
    expect(verified.payload.sub).toBe("ssr-issuer-test-user")
    expect(verified.payload.iss).toBeUndefined()
    await expect(validateJwt(token)).resolves.toEqual(SSR_AUTH_UNAUTH)
  })

  it("real jose accepts a signed token with the right audience but a foreign issuer, while SSR rejects it", async () => {
    const token = await signedToken("https://foreign.example.test")
    await expect(jwtVerify(token, activeKey.publicKey, { audience })).resolves.toMatchObject({
      payload: { sub: "ssr-issuer-test-user", iss: "https://foreign.example.test" },
    })
    await expect(validateJwt(token)).resolves.toEqual(SSR_AUTH_UNAUTH)
  })

  it("normalizes NEL and FS-US edges exactly like Python str.strip before real jose verification", async () => {
    const configuredIssuer = `\u0085\u001C\u001D\u001E\u001F${expectedIssuer}\u001C\u001D\u001E\u001F\u0085`
    vi.stubEnv("JWT_ISSUER", configuredIssuer)
    const token = await signedToken(expectedIssuer)

    await expect(
      jwtVerify(token, activeKey.publicKey, { audience, issuer: expectedIssuer })
    ).resolves.toMatchObject({ payload: { iss: expectedIssuer } })
    await expect(validateJwt(token)).resolves.toMatchObject({
      isAuth: true,
      user: { role: "admin" },
    })
  })

  it("strips the complete Python str.strip whitespace set at issuer edges", async () => {
    const pythonStripWhitespace =
      "\u0009\u000A\u000B\u000C\u000D\u001C\u001D\u001E\u001F\u0020\u0085\u00A0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200A\u2028\u2029\u202F\u205F\u3000"
    const configuredIssuer = pythonStripWhitespace + expectedIssuer + pythonStripWhitespace
    vi.stubEnv("JWT_ISSUER", configuredIssuer)
    const token = await signedToken(expectedIssuer)

    await expect(
      jwtVerify(token, activeKey.publicKey, { audience, issuer: expectedIssuer })
    ).resolves.toMatchObject({ payload: { iss: expectedIssuer } })
    await expect(validateJwt(token)).resolves.toMatchObject({
      isAuth: true,
      user: { role: "admin" },
    })
  })
  it("preserves U+FEFF like Python str.strip and rejects an issuer without it", async () => {
    const configuredIssuer = `\uFEFF${expectedIssuer}\uFEFF`
    vi.stubEnv("JWT_ISSUER", configuredIssuer)
    const exactToken = await signedToken(configuredIssuer)

    await expect(
      jwtVerify(exactToken, activeKey.publicKey, { audience, issuer: configuredIssuer })
    ).resolves.toMatchObject({ payload: { iss: configuredIssuer } })
    await expect(validateJwt(exactToken)).resolves.toMatchObject({ isAuth: true })

    const strippedToken = await signedToken(expectedIssuer)
    await expect(
      jwtVerify(strippedToken, activeKey.publicKey, { audience, issuer: configuredIssuer })
    ).rejects.toThrow()
    await expect(validateJwt(strippedToken)).resolves.toEqual(SSR_AUTH_UNAUTH)
  })

  it("accepts a 512-code-point issuer containing an astral character", async () => {
    const issuer = `${"x".repeat(511)}\u{1F680}`
    expect(Array.from(issuer)).toHaveLength(512)
    expect(issuer.length).toBe(513)
    vi.stubEnv("JWT_ISSUER", issuer)
    const token = await signedToken(issuer)

    await expect(
      jwtVerify(token, activeKey.publicKey, { audience, issuer })
    ).resolves.toMatchObject({
      payload: { iss: issuer },
    })
    await expect(validateJwt(token)).resolves.toMatchObject({ isAuth: true })
  })

  it("rejects a 513-code-point issuer even when real jose accepts its exact claim", async () => {
    const issuer = `${"x".repeat(512)}\u{1F680}`
    expect(Array.from(issuer)).toHaveLength(513)
    expect(issuer.length).toBe(514)
    vi.stubEnv("JWT_ISSUER", issuer)
    const token = await signedToken(issuer)
    const verify = vi.fn(async () => ({ payload: { sub: "oversized-user", iss: issuer } }))
    setJwtVerifyOverrideForTests(verify)

    await expect(
      jwtVerify(token, activeKey.publicKey, { audience, issuer })
    ).resolves.toMatchObject({
      payload: { iss: issuer },
    })
    await expect(validateJwt(token)).resolves.toEqual(SSR_AUTH_UNAUTH)
    expect(verify).not.toHaveBeenCalled()
  })

  it("rejects embedded C0 controls that real jose otherwise verifies exactly", async () => {
    const issuer = `${expectedIssuer}\u001Ctail`
    vi.stubEnv("JWT_ISSUER", issuer)
    const token = await signedToken(issuer)
    const verify = vi.fn(async () => ({ payload: { sub: "control-user", iss: issuer } }))
    setJwtVerifyOverrideForTests(verify)

    await expect(
      jwtVerify(token, activeKey.publicKey, { audience, issuer })
    ).resolves.toMatchObject({
      payload: { iss: issuer },
    })
    await expect(validateJwt(token)).resolves.toEqual(SSR_AUTH_UNAUTH)
    expect(verify).not.toHaveBeenCalled()
  })

  it.each(["previous", "active"] as const)(
    "accepts an issuer-bound token signed by the %s RSA rotation key",
    async (keyKind) => {
      const signingKey = keyKind === "previous" ? previousKey : activeKey
      await expect(
        validateJwt(await signedToken(expectedIssuer, signingKey))
      ).resolves.toMatchObject({
        isAuth: true,
        user: { role: "admin" },
      })
    }
  )

  it("uses the backend issuer default in development when JWT_ISSUER is absent", async () => {
    delete process.env.JWT_ISSUER
    setJwtVerifyOverrideForTests(async () => ({
      payload: { sub: "dev-user", iss: "university-ecosystem", aud: audience },
    }))

    await expect(validateJwt("dev-default-token")).resolves.toMatchObject({ isAuth: true })
  })

  it("rejects an explicitly blank development JWT_ISSUER like backend settings", async () => {
    vi.stubEnv("JWT_ISSUER", " \u0085\u001C\u001F")
    const verify = vi.fn(async () => ({
      payload: { sub: "blank-issuer-user", iss: "university-ecosystem", aud: audience },
    }))
    setJwtVerifyOverrideForTests(verify)

    await expect(validateJwt("blank-development-issuer-token")).resolves.toEqual(SSR_AUTH_UNAUTH)
    expect(verify).not.toHaveBeenCalled()
  })

  it("fails closed in production when JWT_ISSUER is absent", async () => {
    delete process.env.JWT_ISSUER
    vi.stubEnv("NODE_ENV", "production")
    const verify = vi.fn(async () => ({
      payload: { sub: "production-user", iss: "university-ecosystem", aud: audience },
    }))
    setJwtVerifyOverrideForTests(verify)

    await expect(validateJwt("unconfigured-production-token")).resolves.toEqual(SSR_AUTH_UNAUTH)
    expect(verify).not.toHaveBeenCalled()
  })
})
