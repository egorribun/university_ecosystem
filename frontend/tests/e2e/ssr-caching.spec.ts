import { expect, test } from "./test"

test.describe("Production SSR cache policy", () => {
  test.skip(
    process.env.PRODUCTION_SERVER_E2E !== "true",
    "Run this contract with PRODUCTION_SERVER_E2E=true so server-prod.mjs is exercised."
  )

  test("uses immutable caching for assets and no-store for the HTML shell", async ({ request }) => {
    const shell = await request.get("/login")
    expect(shell.ok()).toBeTruthy()
    expect(shell.headers()["content-type"]).toContain("text/html")
    expect(shell.headers()["cache-control"]).toBe("no-store, private, max-age=0")

    const html = await shell.text()
    const assetPath = html.match(/(?:src|href)="(\/assets\/[^"]+)"/)?.[1]
    expect(assetPath).toBeTruthy()

    const asset = await request.get(assetPath as string)
    expect(asset.ok()).toBeTruthy()
    expect(asset.headers()["cache-control"]).toBe("public, max-age=31536000, immutable")

    const serviceWorker = await request.get("/sw.js")
    if (serviceWorker.ok()) {
      expect(serviceWorker.headers()["cache-control"]).toContain("no-store")
    }
  })
})
