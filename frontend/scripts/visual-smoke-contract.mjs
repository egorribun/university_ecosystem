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
