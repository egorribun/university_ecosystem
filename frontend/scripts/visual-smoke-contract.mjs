const HYDRATION_ERROR_PATTERN =
  /hydrat|did not match|Minified React error #(418|419|420|421|422|423|424|425|426|427)/iu
const UNAUTHENTICATED_PROFILE_PATH = "/api/v1/users/me"
const RESOURCE_401_PATTERN = /Failed to load resource:.*status of 401/iu

function hasExactLocation(url, expectedOrigin, expectedPath) {
  try {
    const parsed = new URL(url)
    const origin = new URL(expectedOrigin).origin
    return (
      parsed.origin === origin &&
      parsed.pathname === expectedPath &&
      parsed.search === "" &&
      parsed.hash === ""
    )
  } catch {
    return false
  }
}

function isUnauthenticatedProfileProbe({ method, url, status }, expectedOrigin) {
  return (
    method === "GET" &&
    status === 401 &&
    hasExactLocation(url, expectedOrigin, UNAUTHENTICATED_PROFILE_PATH)
  )
}

export function responseRecord(response) {
  return {
    method: response.request().method(),
    url: response.url(),
    status: response.status(),
  }
}

// The authenticated matrix records request failures without exposing raw destinations.
// This hook is limited to its own process and cannot change the audit outcome.
const VISUAL_ERROR_CODES = new Map([
  ["net::ERR_FAILED", "failed"],
  ["net::ERR_EMPTY_RESPONSE", "empty_response"],
  ["net::ERR_HTTP2_PROTOCOL_ERROR", "http2_protocol_error"],
  ["net::ERR_HTTP2_SERVER_REFUSED_STREAM", "http2_server_refused_stream"],
  ["net::ERR_HTTP2_PING_FAILED", "http2_ping_failed"],
  ["net::ERR_CONTENT_LENGTH_MISMATCH", "content_length_mismatch"],
  ["net::ERR_INCOMPLETE_CHUNKED_ENCODING", "incomplete_chunked_encoding"],
  ["net::ERR_NETWORK_CHANGED", "network_changed"],
  ["net::ERR_INTERNET_DISCONNECTED", "internet_disconnected"],
  ["net::ERR_ADDRESS_UNREACHABLE", "address_unreachable"],
  ["net::ERR_CONNECTION_RESET", "connection_reset"],
  ["net::ERR_CONNECTION_CLOSED", "connection_closed"],
  ["net::ERR_CONNECTION_REFUSED", "connection_refused"],
  ["net::ERR_BLOCKED_BY_CLIENT", "blocked_by_client"],
  ["net::ERR_NAME_NOT_RESOLVED", "name_not_resolved"],
  ["net::ERR_TIMED_OUT", "timed_out"],
])
const VISUAL_API_FAMILIES = [
  "events",
  "news",
  "stories",
  "schedule",
  "notifications",
  "campus",
  "img",
  "auth",
  "push",
  "groups",
  "users",
]
let visualRequestDiagnosticCount = 0

function emitVisualRequestDiagnostic(request, failure, rawErrorText) {
  try {
    const script = process.argv[1]?.replaceAll("\\", "/").split("/").at(-1)
    if (
      process.env.VISUAL_CAPTURE_MATRIX !== "1" ||
      script !== "authenticated-visual-audit.mjs" ||
      // The audit still records aborts; reserve the bounded detail for other failures.
      rawErrorText === "net::ERR_ABORTED" ||
      visualRequestDiagnosticCount >= 64
    )
      return
    const expectedOrigin = new URL(process.env.ORIGIN ?? "http://localhost").origin
    let requestOrigin = "invalid"
    let apiFamily = "other"
    try {
      const parsed = new URL(failure.url)
      requestOrigin = parsed.origin === expectedOrigin ? "same_origin" : "external"
      if (requestOrigin === "same_origin") {
        if (parsed.pathname === "/api/v1/users/me") apiFamily = "profile"
        else {
          for (const family of VISUAL_API_FAMILIES) {
            const prefix = `/api/v1/${family}`
            if (parsed.pathname === prefix || parsed.pathname.startsWith(`${prefix}/`)) {
              apiFamily = family
              break
            }
          }
        }
      }
    } catch {
      // Invalid request URLs stay in the closed invalid/other categories.
    }
    let route = "other"
    let width = 0
    try {
      const page = request.frame().page()
      const current = new URL(page.url())
      if (
        current.origin === expectedOrigin &&
        ["/dashboard", "/events", "/news"].includes(current.pathname)
      )
        route = current.pathname
      const viewportWidth = page.viewportSize()?.width
      if ([360, 375, 390, 414, 768, 1024, 1280, 1440, 1920].includes(viewportWidth)) {
        width = viewportWidth
      }
    } catch {
      // Requests without an accessible page stay in the closed fallback categories.
    }
    let resourceType = "unknown"
    try {
      const type = request.resourceType()
      resourceType = ["image", "xhr", "fetch"].includes(type) ? type : "other"
    } catch {
      // A missing or inaccessible Playwright resource type remains unknown.
    }
    const errorCode =
      typeof rawErrorText !== "string" || rawErrorText === ""
        ? "unknown"
        : (VISUAL_ERROR_CODES.get(rawErrorText) ?? "other")
    const method = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"].includes(
      failure.method
    )
      ? failure.method
      : "other"
    visualRequestDiagnosticCount++
    console.log(
      "visual-request-diagnostics " +
        JSON.stringify({
          schema: 1,
          route,
          width,
          method,
          requestOrigin,
          apiFamily,
          resourceType,
          errorCode,
        })
    )
  } catch {
    // Diagnostics must never alter the failure record or acceptance gate.
  }
}

export function requestFailureRecord(request) {
  const method = request.method()
  const url = request.url()
  const rawErrorText = request.failure()?.errorText
  const failure = { method, url, errorText: rawErrorText ?? "unknown network failure" }
  emitVisualRequestDiagnostic(request, failure, rawErrorText)
  return failure
}

export function classifySmokeRouteOutcome({
  navigationError,
  httpStatus,
  strict,
  hydrationErrorCount,
}) {
  const httpFailure = httpStatus !== null && (httpStatus < 200 || httpStatus >= 400)
  const success = !navigationError && !httpFailure
  return {
    success,
    failed: !success || (strict && hydrationErrorCount > 0),
  }
}

export function classifyAuthenticatedAuditSummaries(summaries) {
  return {
    failedRoutes: summaries.filter(({ httpStatus, redirectedToLogin }) =>
      Boolean(httpStatus !== 200 || redirectedToLogin)
    ),
    hydrationIssues: summaries.filter(({ hydrationErrorCount }) => hydrationErrorCount > 0),
    axeErrors: summaries.filter(({ axeError }) => Boolean(axeError)),
    axeIssues: summaries.filter(({ axeViolationCount }) => axeViolationCount > 0),
    runtimeIssues: summaries.filter(
      ({ consoleErrorCount, failedNetworkRequestCount }) =>
        consoleErrorCount > 0 || failedNetworkRequestCount > 0
    ),
  }
}

export function classifySmokeFailures({
  consoleMessages,
  networkResponses,
  networkFailures = [],
  allowUnauthenticatedProfileProbe = false,
  expectedOrigin = null,
}) {
  const rawConsoleErrors = consoleMessages.filter(
    ({ type }) => type === "error" || type === "pageerror"
  )
  const expectedProbeCount = allowUnauthenticatedProfileProbe
    ? networkResponses.filter((response) => isUnauthenticatedProfileProbe(response, expectedOrigin))
        .length
    : 0
  let remainingProbeConsoleCount = expectedProbeCount
  const consoleErrors = rawConsoleErrors.filter((message) => {
    const locationUrl = message.location?.url
    const isExpectedProbeConsole =
      remainingProbeConsoleCount > 0 &&
      message.type === "error" &&
      typeof locationUrl === "string" &&
      hasExactLocation(locationUrl, expectedOrigin, UNAUTHENTICATED_PROFILE_PATH) &&
      RESOURCE_401_PATTERN.test(message.text)
    if (isExpectedProbeConsole) remainingProbeConsoleCount -= 1
    return !isExpectedProbeConsole
  })
  return {
    consoleErrors,
    hydrationErrors: consoleMessages.filter(({ text }) => HYDRATION_ERROR_PATTERN.test(text)),
    nonSuccessfulResponses: networkResponses.filter(
      (response) =>
        (response.status < 200 || response.status >= 400) &&
        !(
          allowUnauthenticatedProfileProbe &&
          isUnauthenticatedProfileProbe(response, expectedOrigin)
        )
    ),
    networkFailures,
  }
}

// Public diagnostics are bounded metadata, never serialized axe results or DOM nodes.
const AXE_DIAGNOSTIC_ROUTES = new Set([
  "/dashboard",
  "/events",
  "/news",
  "/schedule",
  "/profile",
  "/settings",
  "/map",
  "/activity",
  "/messenger",
])
const AXE_DIAGNOSTIC_IMPACTS = new Set(["minor", "moderate", "serious", "critical"])
const MAX_AXE_DIAGNOSTIC_ENTRIES = 20
const MAX_AXE_DIAGNOSTIC_OUTPUT_LENGTH = 4096

export function summarizeAxeDiagnostics(route, violations, trustedRuleIds) {
  if (!Array.isArray(violations)) throw new TypeError("Invalid axe diagnostics")
  const totalViolationCount = violations.length
  if (!Number.isSafeInteger(totalViolationCount) || totalViolationCount < 0) {
    throw new TypeError("Invalid axe diagnostics")
  }
  let routeLabel = "unknown-route"
  if (typeof route === "string" && route.length <= 64) {
    if (AXE_DIAGNOSTIC_ROUTES.has(route)) routeLabel = route
    else if (
      /^\/messenger\/[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/iu.test(
        route
      )
    ) {
      routeLabel = "/messenger/:id"
    }
  }
  const entries = []
  for (
    let index = 0;
    index < Math.min(totalViolationCount, MAX_AXE_DIAGNOSTIC_ENTRIES);
    index += 1
  ) {
    const violation = violations[index]
    const { id, impact, nodes } = violation && typeof violation === "object" ? violation : {}
    const nodeCount = Array.isArray(nodes) ? nodes.length : 0
    entries.push({
      id:
        typeof id === "string" &&
        /^[a-z][a-z0-9-]{0,63}$/u.test(id) &&
        Set.prototype.has.call(trustedRuleIds, id)
          ? id
          : "unknown-rule",
      impact: AXE_DIAGNOSTIC_IMPACTS.has(impact) ? impact : "unknown-impact",
      nodeCount: Number.isSafeInteger(nodeCount) && nodeCount >= 0 ? nodeCount : 0,
    })
  }
  return {
    route: routeLabel,
    totalViolationCount,
    omittedViolationCount: totalViolationCount - entries.length,
    violations: entries,
  }
}

export function emitAxeDiagnostics(route, violations, loadTrustedRuleIds, write) {
  // Catalog, projection, serialization and output faults cannot affect audit gates.
  try {
    const summary = summarizeAxeDiagnostics(route, violations, loadTrustedRuleIds())
    const encoded = JSON.stringify(summary)
    if (typeof encoded !== "string") return
    const line = "axe-diagnostics " + encoded
    if (line.length > MAX_AXE_DIAGNOSTIC_OUTPUT_LENGTH) return
    const output = write ?? console.log
    output(line)
  } catch {
    // Never serialize the diagnostic error or retry a failing output sink.
  }
}
