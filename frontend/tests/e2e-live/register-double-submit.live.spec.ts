import { expect, test, type Browser, type Request } from "@playwright/test"
import { freshPassword, loginAs, stubBreachedPasswordLookup } from "./fixtures"

function isRegistrationPost(request: Request): boolean {
  return request.method() === "POST" && new URL(request.url()).pathname.endsWith("/auth/register")
}

async function deleteOwnedAccount(browser: Browser, userId: string): Promise<void> {
  const baseURL = process.env.LIVE_BASE_URL
  if (!baseURL) throw new Error("LIVE_BASE_URL must be set by the live acceptance runner")

  const context = await browser.newContext({
    baseURL,
    ignoreHTTPSErrors: true,
    locale: "ru-RU",
  })

  try {
    const adminPage = await context.newPage()
    await loginAs(adminPage, "admin")
    const deletionStatus = await adminPage.evaluate(async (createdUserId) => {
      const csrfCookie = document.cookie
        .split(";")
        .map((part) => part.trim())
        .find((part) => part.startsWith("csrf_token="))
      if (!csrfCookie) return 0

      const csrfToken = decodeURIComponent(csrfCookie.slice("csrf_token=".length))
      const response = await fetch(`/api/v1/users/${encodeURIComponent(createdUserId)}`, {
        method: "DELETE",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "X-CSRF-Token": csrfToken,
          "X-Requested-With": "XMLHttpRequest",
        },
      })
      return response.status
    }, userId)

    expect(
      deletionStatus,
      "cleanup deletes only the account id returned by this registration"
    ).toBe(200)
  } finally {
    await context.close()
  }
}

test("rapid double submit on a 360px registration form creates one account", async ({
  browser,
  page,
  context,
}, testInfo) => {
  const liveBaseUrl = process.env.LIVE_BASE_URL
  if (!liveBaseUrl) throw new Error("LIVE_BASE_URL must be set by the live acceptance runner")

  await page.setViewportSize({ width: 360, height: 800 })
  await context.addCookies([{ name: "ue:language", value: "ru", url: liveBaseUrl }])
  await page.addInitScript(() => window.localStorage.setItem("ue:language", "ru"))
  await stubBreachedPasswordLookup(page)
  await page.goto("/register", { waitUntil: "domcontentloaded" })

  const suffix = crypto.randomUUID()
  const email = `live-double-submit-${suffix}@example.com`
  const fullName = `Live double submit ${suffix.slice(0, 8)}`
  const password = freshPassword()
  await page.locator("#full_name").fill(fullName)
  await page.locator("#email").fill(email)
  await page.locator("#password").fill(password)
  await page.locator("#confirmPassword").fill(password)

  const submitButton = page.locator("#register-submit")
  await expect(submitButton).toBeVisible()
  await expect(submitButton).toBeEnabled()
  await submitButton.scrollIntoViewIfNeeded()

  let registerPostCount = 0
  const createdUserIds = new Set<string>()
  const registrationResponseCaptures: Promise<void>[] = []
  const countRegistrationPosts = (request: Request) => {
    if (!isRegistrationPost(request)) return
    registerPostCount += 1

    registrationResponseCaptures.push(
      request
        .response()
        .then(async (response) => {
          if (!response?.ok()) return
          const body = (await response.json().catch(() => null)) as { id?: unknown } | null
          if (typeof body?.id === "string") createdUserIds.add(body.id)
        })
        .catch(() => undefined)
    )
  }
  page.on("request", countRegistrationPosts)

  const registrationResponsePromise = page
    .waitForResponse((response) => isRegistrationPost(response.request()), { timeout: 15_000 })
    .catch(() => null)
  const cdp = await context.newCDPSession(page)

  try {
    // Keep the real API path but give the UI time to enter its pending state
    // before the second physical input arrives, as on a slow mobile connection.
    await cdp.send("Network.enable")
    await cdp.send("Network.emulateNetworkConditions", {
      offline: false,
      latency: 250,
      downloadThroughput: 1_500_000,
      uploadThroughput: 750_000,
      connectionType: "cellular3g",
    })

    if (testInfo.project.name.toLowerCase().includes("mobile")) {
      const bounds = await submitButton.boundingBox()
      if (!bounds) throw new Error("Registration submit control is not visible")
      const x = bounds.x + bounds.width / 2
      const y = bounds.y + bounds.height / 2
      await page.touchscreen.tap(x, y)
      await page.touchscreen.tap(x, y)
    } else {
      await submitButton.dblclick({ delay: 0 })
    }

    await cdp.send("Network.emulateNetworkConditions", {
      offline: false,
      latency: 0,
      downloadThroughput: -1,
      uploadThroughput: -1,
      connectionType: "none",
    })

    const registrationResponse = await registrationResponsePromise
    if (!registrationResponse) throw new Error("Registration request did not receive a response")
    const registrationBody = (await registrationResponse.json().catch(() => null)) as {
      status?: unknown
      id?: unknown
    } | null

    expect(registrationResponse.status()).toBe(200)
    expect(registrationBody?.status).toBe("ok")
    expect(typeof registrationBody?.id).toBe("string")
    expect(registerPostCount).toBe(1)
    await expect(page).toHaveURL(/\/login$/u)
    await expect(page.locator("main.auth-shell--login")).toBeVisible()
  } finally {
    page.off("request", countRegistrationPosts)
    await cdp.detach()
    await Promise.all(registrationResponseCaptures)
    for (const userId of createdUserIds) await deleteOwnedAccount(browser, userId)
  }
})
