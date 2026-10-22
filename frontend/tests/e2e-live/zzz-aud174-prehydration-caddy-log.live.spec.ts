import { expect, test } from "@playwright/test"
import { writeFile } from "node:fs/promises"
import { join } from "node:path"

test.describe.configure({ retries: 0 })
test.use({ javaScriptEnabled: false })

test("pre-hydration login remains inert and the live Caddy log redacts its query", async ({
  page,
}, testInfo) => {
  const nonce = process.env.LIVE_CADDY_LOG_PROBE
  const correlationSource = process.env.LIVE_CADDY_PROBE_IDS
  const liveBaseUrl = process.env.LIVE_BASE_URL
  const outputDirectory = process.env.LIVE_E2E_OUTPUT_DIR
  if (
    !nonce ||
    !/^[0-9a-f]{32}$/u.test(nonce) ||
    !correlationSource ||
    !liveBaseUrl ||
    !outputDirectory
  ) {
    throw new Error("the owned live Caddy query probe is not configured")
  }

  let correlationIds: Record<string, string>
  try {
    correlationIds = JSON.parse(correlationSource) as Record<string, string>
  } catch {
    throw new Error("the owned live Caddy query probe is not configured")
  }
  const projectName = testInfo.project.name
  const correlationId = correlationIds[projectName]
  if (!correlationId || !/^[0-9a-f]{32}$/u.test(correlationId) || correlationId === nonce) {
    throw new Error("the owned live Caddy query probe is not configured")
  }

  const liveOrigin = new URL(liveBaseUrl).origin
  const loginDocumentRequests: Array<{ method: string; hasSearch: boolean }> = []
  page.on("request", (request) => {
    if (request.resourceType() !== "document") return
    const requestedUrl = new URL(request.url())
    if (requestedUrl.origin !== liveOrigin || requestedUrl.pathname !== "/login") return
    loginDocumentRequests.push({
      method: request.method(),
      hasSearch: requestedUrl.search.length > 0,
    })
  })

  await page.goto("/login", { waitUntil: "domcontentloaded" })

  const loginForm = page.locator("form")
  await expect(loginForm).toHaveAttribute("method", "post")
  expect(await loginForm.getAttribute("action")).toBeNull()
  expect(new URL(page.url()).pathname).toBe("/login")
  expect(new URL(page.url()).search).toBe("")
  await expect(page.locator("#email")).toBeDisabled()
  await expect(page.locator("#password")).toBeDisabled()
  await expect(page.locator("#login-submit")).toBeDisabled()
  expect(await page.evaluate(() => window.__APP_HYDRATED === true)).toBe(false)
  expect(loginDocumentRequests).toEqual([{ method: "GET", hasSearch: false }])

  const probeUrl = new URL("/login", liveBaseUrl)
  probeUrl.searchParams.set("probe", correlationId)
  probeUrl.searchParams.set("password", `${nonce}-${projectName}`)
  let responseStatus: number
  try {
    const response = await page.request.get(probeUrl.toString(), { timeout: 10_000 })
    try {
      responseStatus = response.status()
    } finally {
      await response.dispose()
    }
  } catch {
    throw new Error("the owned live Caddy query probe request failed")
  } finally {
    probeUrl.search = ""
  }
  if (responseStatus !== 200) {
    throw new Error("the owned live Caddy query probe response was not successful")
  }

  const observation = {
    schema: "aud174-caddy-probe-v1",
    project: projectName,
    completed_at_ms: Date.now(),
  }
  const observationPath = join(outputDirectory, `aud174-caddy-probe-${projectName}.json`)
  try {
    await writeFile(observationPath, JSON.stringify(observation), {
      encoding: "utf8",
      flag: "wx",
      mode: 0o600,
    })
  } catch {
    throw new Error("the owned live Caddy query probe observation could not be recorded")
  }
})
