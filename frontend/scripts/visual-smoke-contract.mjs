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

export function requestFailureRecord(request) {
  return {
    method: request.method(),
    url: request.url(),
    errorText: request.failure()?.errorText ?? "unknown network failure",
  }
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
