import { expect, test } from "./test"

declare global {
  interface Window {
    __ueTrustedRan?: boolean
    __ueUntrustedRan?: boolean
    __ueViolations?: string[]
  }
}

/**
 * AUD-231: the enforcing CSP on SSR documents must stop an untrusted inline script in a real
 * browser, while a script carrying the response's own nonce still runs. The document is
 * intercepted and an untrusted script is added to the server's HTML; headers are kept as served.
 */
test.describe("SSR document CSP in a browser", () => {
  test.skip(
    process.env.PRODUCTION_SERVER_E2E !== "true",
    "Run with PRODUCTION_SERVER_E2E=true so the compiled SSR server (server-prod.mjs) serves the document."
  )

  test("blocks an untrusted inline script and runs only the nonce-bearing one", async ({
    page,
  }) => {
    let served: { nonce: string; csp: string } | null = null

    await page.route("**/*", async (route) => {
      if (route.request().resourceType() !== "document") {
        await route.continue()
        return
      }
      const response = await route.fetch()
      const csp = response.headers()["content-security-policy"] ?? ""
      const nonce = csp.match(/script-src[^;]*'nonce-([^']+)'/u)?.[1]
      const html = await response.text()
      if (!nonce || !html.includes("</body>")) {
        await route.fulfill({ response, body: html })
        return
      }
      served = { nonce, csp }
      const injected = html.replace(
        "</body>",
        "<script>window.__ueUntrustedRan = true</script>" +
          `<script nonce="${nonce}">window.__ueTrustedRan = true</script></body>`
      )
      await route.fulfill({ response, body: injected })
    })

    await page.addInitScript(() => {
      const violations: string[] = []
      Object.defineProperty(window, "__ueViolations", { value: violations })
      document.addEventListener("securitypolicyviolation", (event) => {
        violations.push(`${event.effectiveDirective}|${event.sample}`)
      })
    })

    const response = await page.goto("/login")
    expect(response?.status()).toBeLessThan(500)

    await expect.poll(() => page.evaluate(() => window.__ueTrustedRan === true)).toBe(true)
    expect(served).not.toBeNull()
    expect(served!.csp).toContain("script-src 'self' 'nonce-")
    expect(await page.evaluate(() => window.__ueUntrustedRan)).toBeUndefined()

    const violations = await page.evaluate(() => window.__ueViolations as string[])
    expect(
      violations.some(
        (entry) => entry.startsWith("script-src") && entry.includes("__ueUntrustedRan")
      )
    ).toBe(true)
  })
})
