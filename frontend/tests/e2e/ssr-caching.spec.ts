import { expect, test } from "./test"

function nonceFromPolicy(policy: string | undefined): string {
  const nonce = policy?.match(/script-src[^;]*'nonce-([^']+)'/u)?.[1]
  if (!nonce) throw new Error("SSR response is missing its CSP nonce")
  return nonce
}

function expectNativeNoncePair(headers: Record<string, string>, html: string): string {
  const nonce = nonceFromPolicy(headers["content-security-policy"])
  expect(headers["content-security-policy-report-only"]).toContain(`'nonce-${nonce}'`)

  const nonceMeta = html
    .match(/<meta\b[^>]*>/gu)
    ?.find((tag) => /\bproperty="csp-nonce"/u.test(tag))
  const metaNonce = nonceMeta?.match(/\bcontent="([^"]+)"/u)?.[1]
  expect(metaNonce).toBe(nonce)

  // RootShell emits a trusted inline bootstrap; an external bundle nonce alone is insufficient.
  const inlineScripts = Array.from(html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/giu))
  expect(
    inlineScripts.some(
      ([, attributes = "", body = ""]) =>
        !/(?:^|\s)src\s*=/iu.test(attributes) &&
        attributes.match(/(?:^|\s)nonce\s*=\s*"([^"]+)"/iu)?.[1] === nonce &&
        body.trim().length > 0
    )
  ).toBe(true)
  expect(headers["cache-control"]).toBe("no-store, private, max-age=0")
  expect(headers.etag).toBeUndefined()
  expect(headers["last-modified"]).toBeUndefined()
  return nonce
}

test.describe("Production SSR cache policy", () => {
  test.skip(
    process.env.PRODUCTION_SERVER_E2E !== "true",
    "Run this contract with PRODUCTION_SERVER_E2E=true so server-prod.mjs is exercised."
  )

  test("pairs concurrent HTML nonces and keeps the shell private while caching assets", async ({
    request,
  }) => {
    const [firstShell, secondShell] = await Promise.all([
      request.get("/login"),
      request.get("/login"),
    ])
    expect(firstShell.ok()).toBeTruthy()
    expect(secondShell.ok()).toBeTruthy()
    expect(firstShell.headers()["content-type"]).toContain("text/html")
    expect(secondShell.headers()["content-type"]).toContain("text/html")

    const [html, secondHtml] = await Promise.all([firstShell.text(), secondShell.text()])
    const firstNonce = expectNativeNoncePair(firstShell.headers(), html)
    const secondNonce = expectNativeNoncePair(secondShell.headers(), secondHtml)
    expect(firstNonce).not.toBe(secondNonce)
    const assetPath = html.match(/(?:src|href)="(\/assets\/[^"]+)"/)?.[1]
    expect(assetPath).toBeTruthy()

    const asset = await request.get(assetPath as string)
    expect(asset.ok()).toBeTruthy()
    expect(asset.headers()["cache-control"]).toBe("public, max-age=31536000, immutable")

    const serviceWorker = await request.get("/sw.js")
    if (serviceWorker.ok()) {
      expect(serviceWorker.headers()["cache-control"]).toContain("no-store")
    }

    const health = await request.get("/healthz")
    expect(health.ok()).toBeTruthy()
    expect(health.headers()["content-type"]).toContain("application/json")
    expect(health.headers()["cache-control"]).toBe("no-store")
    expect(health.headers()["content-security-policy"]).toBeUndefined()
    expect(health.headers()["content-security-policy-report-only"]).toBeUndefined()
    await expect(health.json()).resolves.toEqual({ status: "ok" })
  })
})
