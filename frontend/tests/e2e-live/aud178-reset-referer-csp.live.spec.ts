import { randomUUID } from "node:crypto"
import { expect, test } from "@playwright/test"

test.describe.configure({ retries: 0 })

test("reset fragment stays out of browser Referer and CSP report traffic", async ({ page }) => {
  const marker = `synthetic-${randomUUID()}`
  const probe = randomUUID()
  const target = new URL("/reset-password", process.env.LIVE_BASE_URL)
  target.hash = `token=${encodeURIComponent(marker)}`

  // Never let a navigation exception include the synthetic URL in diagnostics.
  const response = await page.goto(target.href).catch(() => {
    throw new Error("The reset-page navigation failed")
  })
  expect(response?.status() === 200).toBe(true)
  const responseHeaders = response!.headers()
  expect(responseHeaders["referrer-policy"]?.toLowerCase() === "no-referrer").toBe(true)
  expect(
    responseHeaders["content-security-policy-report-only"]?.includes("/api/v1/csp-report")
  ).toBe(true)
  const documentRequestSafe = !response!.request().url().includes(marker)
  expect(documentRequestSafe).toBe(true)

  await expect(page.locator("#reset-password-input")).toBeVisible()
  const fragmentStillPresent = await page.evaluate(
    (candidate) => window.location.hash.includes(candidate),
    marker
  )
  expect(fragmentStillPresent).toBe(true)

  const nextRequest = page.waitForRequest((request) => {
    const url = new URL(request.url())
    return url.pathname === "/healthz" && url.searchParams.get("aud178") === probe
  })
  await page.evaluate(async (correlation) => {
    await fetch(`/healthz?aud178=${encodeURIComponent(correlation)}`, { cache: "no-store" })
  }, probe)
  const request = await nextRequest
  const requestHeaders = await request.allHeaders()
  const refererSafe = !(requestHeaders.referer ?? "").includes(marker)
  expect(refererSafe).toBe(true)
  expect(requestHeaders.referer === undefined).toBe(true)
  const probeResponse = await request.response()
  expect(probeResponse !== null && !probeResponse.fromServiceWorker()).toBe(true)

  // Trigger the real page's report-only CSP without putting the marker into
  // the injected action, then inspect the actual browser POST and response.
  const reportPromise = page.waitForRequest((candidate) => {
    const url = new URL(candidate.url())
    return (
      candidate.method() === "POST" &&
      url.pathname === "/api/v1/csp-report" &&
      (candidate.postData() ?? "").includes("aud178.invalid")
    )
  })
  await page.evaluate(async () => {
    await fetch("https://aud178.invalid/csp-probe").catch(() => undefined)
  })
  const report = await reportPromise
  const reportBodySafe = !(report.postData() ?? "").includes(marker)
  const reportHeaders = await report.allHeaders()
  const reportRefererSafe = !(reportHeaders.referer ?? "").includes(marker)
  expect(reportBodySafe).toBe(true)
  expect(reportRefererSafe).toBe(true)
  expect(reportHeaders.referer === undefined).toBe(true)
  const reportResponse = await report.response()
  expect(
    reportResponse !== null &&
      reportResponse.status() === 204 &&
      !reportResponse.fromServiceWorker()
  ).toBe(true)
})
