const HYDRATION_ERROR_PATTERN =
  /hydrat|did not match|Minified React error #(418|419|420|421|422|423|424|425|426|427)/iu
const UNAUTHENTICATED_PROFILE_PATH = "/api/v1/users/me"
const RESOURCE_401_PATTERN = /Failed to load resource:.*status of 401/iu

function hasExactPath(url, expectedPath) {
  try {
    const parsed = new URL(url)
    return parsed.pathname === expectedPath && parsed.search === "" && parsed.hash === ""
  } catch {
    return false
  }
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
}) {
  const rawConsoleErrors = consoleMessages.filter(
    ({ type }) => type === "error" || type === "pageerror"
  )
  const expectedProbeIndex = allowUnauthenticatedProfileProbe
    ? networkResponses.findIndex(
        ({ method, url, status }) =>
          method === "GET" && status === 401 && hasExactPath(url, UNAUTHENTICATED_PROFILE_PATH)
      )
    : -1
  let probeConsoleConsumed = false
  const consoleErrors = rawConsoleErrors.filter((message) => {
    const locationUrl = message.location?.url
    const isExpectedProbeConsole =
      expectedProbeIndex >= 0 &&
      !probeConsoleConsumed &&
      message.type === "error" &&
      typeof locationUrl === "string" &&
      hasExactPath(locationUrl, UNAUTHENTICATED_PROFILE_PATH) &&
      RESOURCE_401_PATTERN.test(message.text)
    if (isExpectedProbeConsole) probeConsoleConsumed = true
    return !isExpectedProbeConsole
  })
  return {
    consoleErrors,
    hydrationErrors: consoleMessages.filter(({ text }) => HYDRATION_ERROR_PATTERN.test(text)),
    nonSuccessfulResponses: networkResponses.filter(
      ({ status }, index) => (status < 200 || status >= 400) && index !== expectedProbeIndex
    ),
    networkFailures,
  }
}
