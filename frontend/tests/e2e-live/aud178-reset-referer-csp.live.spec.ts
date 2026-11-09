import { randomUUID } from "node:crypto"
import { writeFile } from "node:fs/promises"
import { join } from "node:path"
import { expect, test } from "@playwright/test"

test.describe.configure({ retries: 0 })
// The spec proves what the edge and the network do, and it already rejects any
// response a service worker produced. A worker registered by the first page could
// otherwise take over the later legacy navigations in this context at random.
test.use({ serviceWorkers: "block" })

function reportNamesResetDocument(body: string | null, expectedOrigin: string) {
  try {
    const report = JSON.parse(body ?? "") as { "csp-report"?: { "document-uri"?: unknown } }
    const documentUri = report["csp-report"]?.["document-uri"]
    if (typeof documentUri !== "string") return false
    const document = new URL(documentUri)
    return (
      document.origin === expectedOrigin &&
      document.pathname === "/reset-password" &&
      document.search === "" &&
      document.hash === ""
    )
  } catch {
    return false
  }
}

function isLocalCspProbe(body: string | null) {
  try {
    const report = JSON.parse(body ?? "") as {
      "csp-report"?: { "blocked-uri"?: unknown; "effective-directive"?: unknown }
    }
    return (
      report["csp-report"]?.["blocked-uri"] === "data" &&
      report["csp-report"]?.["effective-directive"] === "connect-src"
    )
  } catch {
    return false
  }
}

type ResetLogProbeBinding = { marker: string; correlationId: string }
type ResetLogProbeBindings = Record<"query" | "path", ResetLogProbeBinding>

function readResetLogProbeBindings(source: string | undefined, project: string) {
  if (!source) throw new Error("The owned reset log probe is not configured")

  let parsed: unknown
  try {
    parsed = JSON.parse(source)
  } catch {
    throw new Error("The owned reset log probe is not configured")
  }

  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("The owned reset log probe is not configured")
  }
  const projectBindings = (parsed as Record<string, unknown>)[project]
  if (
    typeof projectBindings !== "object" ||
    projectBindings === null ||
    Array.isArray(projectBindings)
  ) {
    throw new Error("The owned reset log probe is not configured")
  }

  const typedBindings = projectBindings as Record<string, unknown>
  if (Object.keys(typedBindings).sort().join(",") !== "path,query") {
    throw new Error("The owned reset log probe is not configured")
  }

  const result = {} as ResetLogProbeBindings
  for (const sourceKind of ["query", "path"] as const) {
    const candidate = typedBindings[sourceKind]
    if (typeof candidate !== "object" || candidate === null || Array.isArray(candidate)) {
      throw new Error("The owned reset log probe is not configured")
    }
    const binding = candidate as Record<string, unknown>
    if (
      Object.keys(binding).sort().join(",") !== "correlationId,marker" ||
      typeof binding.marker !== "string" ||
      !/^[0-9a-f]{32}$/u.test(binding.marker) ||
      typeof binding.correlationId !== "string" ||
      !/^[0-9a-f]{32}$/u.test(binding.correlationId) ||
      binding.marker === binding.correlationId
    ) {
      throw new Error("The owned reset log probe is not configured")
    }
    result[sourceKind] = {
      marker: binding.marker,
      correlationId: binding.correlationId,
    }
  }
  if (result.query.marker === result.path.marker) {
    throw new Error("The owned reset log probe is not configured")
  }
  return result
}

async function writeResetLogProbeObservation(
  outputDirectory: string | undefined,
  project: string,
  completedAt: Record<"query" | "path", number>
) {
  if (!outputDirectory) throw new Error("The owned reset log probe is not configured")
  const observation = {
    schema: "aud178-reset-caddy-probe-v1",
    project,
    query_completed_at_ms: completedAt.query,
    path_completed_at_ms: completedAt.path,
  }
  try {
    await writeFile(
      join(outputDirectory, `aud178-reset-caddy-probe-${project}.json`),
      JSON.stringify(observation),
      { encoding: "utf8", flag: "wx", mode: 0o600 }
    )
  } catch {
    throw new Error("The owned reset log probe observation could not be recorded")
  }
}

test("reset fragment stays out of browser Referer and CSP report traffic", async ({
  page,
}, testInfo) => {
  const projectName = testInfo.project.name
  const resetLogBindings = readResetLogProbeBindings(
    process.env.LIVE_AUD178_PROBE_MARKERS,
    projectName
  )
  const resetLogObservation: Record<"query" | "path", number> = { query: 0, path: 0 }
  const outputDirectory = process.env.LIVE_E2E_OUTPUT_DIR
  const marker = `synthetic-${randomUUID()}`
  const probe = randomUUID()
  const target = new URL("/reset-password", process.env.LIVE_BASE_URL)
  target.hash = `token=${encodeURIComponent(marker)}`

  // The stand is loopback-only. Abort any application-initiated cross-origin
  // traffic, including optional telemetry and font requests.
  await page.route("**/*", async (route) => {
    if (new URL(route.request().url()).origin !== target.origin) {
      await route.abort()
      return
    }
    await route.continue()
  })

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
      isLocalCspProbe(candidate.postData())
    )
  })
  await page.evaluate(async () => {
    await fetch("data:text/plain,aud178-csp-probe").catch(() => undefined)
  })
  const report = await reportPromise
  expect(reportNamesResetDocument(report.postData(), target.origin)).toBe(true)
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

  // Legacy links can carry the token in the request path or query until the
  // client migrates them. Probe before any page script runs so a later URL
  // replacement cannot hide a report generated by the initial document.
  const earlyReportLeaks: boolean[] = []
  for (const source of ["query", "path"] as const) {
    const legacyPage = await page.context().newPage()
    let releaseScripts: () => void = () => undefined
    const scriptGate = new Promise<void>((resolve) => {
      releaseScripts = resolve
    })
    try {
      const resetBinding = resetLogBindings[source]
      const legacyMarker = resetBinding.marker
      const earlyCorrelation = randomUUID()
      const legacyTarget = new URL("/reset-password", process.env.LIVE_BASE_URL)
      if (source === "query") {
        legacyTarget.searchParams.set("token", legacyMarker)
      } else {
        legacyTarget.pathname += `/${encodeURIComponent(legacyMarker)}`
      }

      let sawLegacyDocumentRequest = false
      legacyPage.on("request", (candidate) => {
        if (candidate.isNavigationRequest() && candidate.url().includes(legacyMarker)) {
          sawLegacyDocumentRequest = true
        }
      })
      // Hold real script requests until the initial violation is delivered.
      // This prevents the client migration racing the browser's CSP report.
      await legacyPage.route("**/*", async (route) => {
        if (new URL(route.request().url()).origin !== legacyTarget.origin) {
          await route.abort()
          return
        }
        if (route.request().resourceType() === "script") await scriptGate
        const requestUrl = new URL(route.request().url())
        const isLegacyDocumentRequest =
          route.request().isNavigationRequest() &&
          requestUrl.pathname === legacyTarget.pathname &&
          requestUrl.search === legacyTarget.search
        // Header overrides from route.continue are kept across redirects, so the
        // clean document would carry the selector too. Send the token-bearing
        // request with it and hand the browser that 302 unchanged; the browser then
        // requests the clean document itself, without the selector.
        if (isLegacyDocumentRequest) {
          const requestHeaders = await route.request().allHeaders()
          requestHeaders["x-aud178-correlation"] = resetBinding.correlationId
          const redirect = await route.fetch({ headers: requestHeaders, maxRedirects: 0 })
          await route.fulfill({ response: redirect }).catch(() => undefined)
          return
        }
        await route.continue().catch(() => undefined)
      })
      await legacyPage.addInitScript(
        ({ candidate, correlation }) => {
          if (window.top !== window) return
          const initialUrl = new URL(window.location.href)
          Object.assign(window, {
            __aud178Early: {
              beforeHydration: window.__APP_HYDRATED !== true,
              markerInPathOrSearch: (initialUrl.pathname + initialUrl.search).includes(candidate),
              fragmentHasLegacyToken:
                new URLSearchParams(initialUrl.hash.slice(1)).get("legacy-token") === candidate,
              sanitizedResetUrl:
                initialUrl.pathname === "/reset-password" &&
                !initialUrl.searchParams.has("token") &&
                !initialUrl.search.includes(candidate),
            },
          })
          void fetch(`/healthz?aud178=${encodeURIComponent(correlation)}`, {
            cache: "no-store",
          }).catch(() => undefined)
          void fetch("data:text/plain,aud178-csp-probe").catch(() => undefined)
        },
        { candidate: legacyMarker, correlation: earlyCorrelation }
      )

      const earlyHealthPromise = legacyPage
        .waitForRequest((candidate) => {
          const url = new URL(candidate.url())
          return url.pathname === "/healthz" && url.searchParams.get("aud178") === earlyCorrelation
        })
        .catch(() => null)
      const earlyReportPromise = legacyPage
        .waitForRequest((candidate) => {
          const url = new URL(candidate.url())
          return (
            candidate.method() === "POST" &&
            url.pathname === "/api/v1/csp-report" &&
            isLocalCspProbe(candidate.postData())
          )
        })
        .catch(() => null)
      const legacyResponse = await legacyPage
        .goto(legacyTarget.href, { waitUntil: "commit" })
        .catch(() => {
          throw new Error("The legacy reset-page navigation failed")
        })
      expect(legacyResponse?.status() === 200).toBe(true)
      expect(legacyResponse !== null && !legacyResponse.fromServiceWorker()).toBe(true)
      expect(legacyResponse!.headers()["referrer-policy"]?.toLowerCase() === "no-referrer").toBe(
        true
      )
      expect(sawLegacyDocumentRequest).toBe(true)
      const redirectedRequest = legacyResponse!.request().redirectedFrom()
      const redirectResponse = await redirectedRequest?.response()
      expect(redirectResponse?.status() === 302).toBe(true)
      expect(redirectResponse?.headers()["cache-control"]?.includes("no-store") === true).toBe(true)
      const redirectLocation = redirectResponse?.headers().location
      const redirectTarget = redirectLocation ? new URL(redirectLocation, legacyTarget) : null
      expect(
        redirectTarget !== null &&
          redirectTarget.origin === legacyTarget.origin &&
          redirectTarget.pathname === "/reset-password" &&
          redirectTarget.search === "" &&
          new URLSearchParams(redirectTarget.hash.slice(1)).get("legacy-token") === legacyMarker
      ).toBe(true)
      resetLogObservation[source] = Date.now()
      expect(!legacyResponse!.request().url().includes(legacyMarker)).toBe(true)

      await legacyPage.waitForFunction(() => "__aud178Early" in window, undefined, {
        timeout: 15_000,
      })
      const early = await legacyPage.evaluate(() => {
        const state = (
          window as Window & {
            __aud178Early?: {
              beforeHydration: boolean
              markerInPathOrSearch: boolean
              fragmentHasLegacyToken: boolean
              sanitizedResetUrl: boolean
            }
          }
        ).__aud178Early
        return state
      })
      expect(early?.beforeHydration === true).toBe(true)
      expect(early?.markerInPathOrSearch === false).toBe(true)
      expect(early?.sanitizedResetUrl === true).toBe(true)
      expect(early?.fragmentHasLegacyToken === true).toBe(true)

      const earlyHealth = await earlyHealthPromise
      if (!earlyHealth) throw new Error("The early reset-page health request was not observed")
      const earlyHealthHeaders = await earlyHealth.allHeaders()
      expect(earlyHealthHeaders.referer === undefined).toBe(true)
      const earlyHealthResponse = await earlyHealth.response()
      expect(
        earlyHealthResponse !== null &&
          earlyHealthResponse.status() === 200 &&
          !earlyHealthResponse.fromServiceWorker()
      ).toBe(true)

      const earlyReport = await earlyReportPromise
      if (!earlyReport) throw new Error("The early reset-page CSP report was not observed")
      const earlyReportBody = earlyReport.postData()
      expect(reportNamesResetDocument(earlyReportBody, legacyTarget.origin)).toBe(true)
      earlyReportLeaks.push((earlyReportBody ?? "").includes(legacyMarker))
      const earlyReportHeaders = await earlyReport.allHeaders()
      expect(earlyReportHeaders.referer === undefined).toBe(true)
      const earlyReportResponse = await earlyReport.response()
      expect(
        earlyReportResponse !== null &&
          earlyReportResponse.status() === 204 &&
          !earlyReportResponse.fromServiceWorker()
      ).toBe(true)
      const stillEarly = await legacyPage.evaluate((candidate) => {
        const current = new URL(window.location.href)
        const initial = (window as Window & { __aud178Early?: { markerInPathOrSearch: boolean } })
          .__aud178Early
        return (
          window.__APP_HYDRATED !== true &&
          (current.pathname + current.search).includes(candidate) === initial?.markerInPathOrSearch
        )
      }, legacyMarker)
      expect(stillEarly).toBe(true)

      releaseScripts()
      await expect
        .poll(() =>
          legacyPage.evaluate((candidate) => {
            const current = new URL(window.location.href)
            return {
              resetRoute: current.pathname === "/reset-password",
              queryClear: !current.searchParams.has("token"),
              tokenAbsent: !current.href.includes(candidate),
              fragmentClear: !new URLSearchParams(current.hash.slice(1)).has("legacy-token"),
              hydrated: window.__APP_HYDRATED === true,
            }
          }, legacyMarker)
        )
        .toEqual({
          resetRoute: true,
          queryClear: true,
          tokenAbsent: true,
          fragmentClear: true,
          hydrated: true,
        })

      const lateReportPromise = legacyPage
        .waitForRequest((candidate) => {
          const url = new URL(candidate.url())
          return (
            candidate.method() === "POST" &&
            url.pathname === "/api/v1/csp-report" &&
            isLocalCspProbe(candidate.postData())
          )
        })
        .catch(() => null)
      await legacyPage.evaluate(async () => {
        await fetch("data:text/plain,aud178-csp-probe").catch(() => undefined)
      })
      const lateReport = await lateReportPromise
      if (!lateReport) throw new Error("The migrated reset-page CSP report was not observed")
      const lateReportBody = lateReport.postData()
      expect(reportNamesResetDocument(lateReportBody, legacyTarget.origin)).toBe(true)
      const lateReportSafe = !(lateReportBody ?? "").includes(legacyMarker)
      expect(lateReportSafe).toBe(true)
      const lateReportHeaders = await lateReport.allHeaders()
      expect(lateReportHeaders.referer === undefined).toBe(true)
      const lateReportResponse = await lateReport.response()
      expect(
        lateReportResponse !== null &&
          lateReportResponse.status() === 204 &&
          !lateReportResponse.fromServiceWorker()
      ).toBe(true)
    } finally {
      releaseScripts()
      await legacyPage.close()
    }
  }
  expect(earlyReportLeaks).toEqual([false, false])
  await writeResetLogProbeObservation(outputDirectory, projectName, resetLogObservation)
})
