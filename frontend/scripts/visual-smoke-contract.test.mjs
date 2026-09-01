import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"

import {
  classifyAuthenticatedAuditSummaries,
  classifySmokeFailures,
  requestFailureRecord,
  responseRecord,
} from "./visual-smoke-contract.mjs"

test("unauthenticated smoke blocks service workers for deterministic SSR lifecycle", async () => {
  const source = await readFile(
    new URL("./unauthenticated-routes-smoke.mjs", import.meta.url),
    "utf8"
  )

  assert.match(
    source,
    /browser\.newContext\(\{[\s\S]*serviceWorkers:\s*["']block["']/u,
    "SSR smoke must not allow a PWA service worker to replace or hold the document while it closes"
  )
})

test("authenticated audit classification fails closed when axe never completes", () => {
  const failures = classifyAuthenticatedAuditSummaries([
    {
      httpStatus: 200,
      redirectedToLogin: false,
      hydrationErrorCount: 0,
      axeError: "axe-analyze-timeout-60s",
      axeViolationCount: 0,
      consoleErrorCount: 0,
      failedNetworkRequestCount: 0,
    },
  ])

  assert.equal(failures.axeErrors.length, 1)
  assert.deepEqual(failures.axeIssues, [])
})

test("responseRecord binds status and method to the response URL", () => {
  const record = responseRecord({
    url: () => "http://localhost/api/v1/users/me",
    status: () => 401,
    request: () => ({ method: () => "GET" }),
  })

  assert.deepEqual(record, {
    method: "GET",
    url: "http://localhost/api/v1/users/me",
    status: 401,
  })
})

test("requestFailureRecord binds transport failures to their request URL", () => {
  assert.deepEqual(
    requestFailureRecord({
      method: () => "GET",
      url: () => "http://localhost/assets/missing.js",
      failure: () => ({ errorText: "net::ERR_CONNECTION_RESET" }),
    }),
    {
      method: "GET",
      url: "http://localhost/assets/missing.js",
      errorText: "net::ERR_CONNECTION_RESET",
    }
  )
})

test("classifySmokeFailures rejects console errors, page errors, and non-2xx/3xx responses", () => {
  const failures = classifySmokeFailures({
    consoleMessages: [
      { type: "warning", text: "allowed warning" },
      { type: "error", text: "request failed" },
      { type: "pageerror", text: "render exploded" },
    ],
    networkResponses: [
      { method: "GET", url: "http://localhost/ok", status: 200 },
      { method: "GET", url: "http://localhost/redirect", status: 302 },
      { method: "GET", url: "http://localhost/api/v1/users/me", status: 401 },
    ],
    networkFailures: [{ method: "GET", url: "http://localhost/assets/app.js", errorText: "reset" }],
  })

  assert.equal(failures.consoleErrors.length, 2)
  assert.deepEqual(failures.nonSuccessfulResponses, [
    { method: "GET", url: "http://localhost/api/v1/users/me", status: 401 },
  ])
  assert.equal(failures.networkFailures.length, 1)
})

test("classifySmokeFailures recognizes minified and descriptive hydration failures", () => {
  const failures = classifySmokeFailures({
    consoleMessages: [
      { type: "error", text: "Minified React error #418" },
      { type: "error", text: "Hydration did not match" },
    ],
    networkResponses: [],
  })

  assert.equal(failures.hydrationErrors.length, 2)
})

test("classifySmokeFailures accepts exactly one located unauthenticated profile probe", () => {
  const failures = classifySmokeFailures({
    allowUnauthenticatedProfileProbe: true,
    expectedOrigin: "http://localhost",
    consoleMessages: [
      {
        type: "error",
        text: "Failed to load resource: the server responded with a status of 401 (Unauthorized)",
        location: { url: "http://localhost/api/v1/users/me" },
      },
    ],
    networkResponses: [{ method: "GET", url: "http://localhost/api/v1/users/me", status: 401 }],
  })

  assert.deepEqual(failures.consoleErrors, [])
  assert.deepEqual(failures.nonSuccessfulResponses, [])
})

test("classifySmokeFailures accepts every exact profile probe without hiding unrelated failures", () => {
  const failures = classifySmokeFailures({
    allowUnauthenticatedProfileProbe: true,
    expectedOrigin: "http://localhost",
    consoleMessages: [
      {
        type: "error",
        text: "Failed to load resource: the server responded with a status of 401 (Unauthorized)",
        location: { url: "http://localhost/api/v1/users/me" },
      },
      {
        type: "error",
        text: "Failed to load resource: the server responded with a status of 401 (Unauthorized)",
        location: { url: "http://localhost/api/v1/users/me" },
      },
      {
        type: "error",
        text: "Failed to load resource: the server responded with a status of 401 (Unauthorized)",
        location: { url: "http://localhost/api/v1/admin" },
      },
      {
        type: "pageerror",
        text: "Failed to load resource: the server responded with a status of 401 (Unauthorized)",
        location: { url: "http://localhost/api/v1/users/me" },
      },
      {
        type: "error",
        text: "profile request failed with 401",
        location: { url: "http://localhost/api/v1/users/me" },
      },
      {
        type: "error",
        text: "Failed to load resource: the server responded with a status of 401 (Unauthorized)",
        location: { url: "http://localhost/api/v1/users/me?retry=1" },
      },
    ],
    networkResponses: [
      { method: "GET", url: "http://localhost/api/v1/users/me", status: 401 },
      { method: "GET", url: "http://localhost/api/v1/users/me", status: 401 },
      { method: "GET", url: "http://localhost/api/v1/admin", status: 401 },
      { method: "POST", url: "http://localhost/api/v1/users/me", status: 401 },
      { method: "GET", url: "http://localhost/api/v1/users/me", status: 403 },
      { method: "GET", url: "http://localhost/api/v1/users/me?retry=1", status: 401 },
    ],
  })

  assert.equal(failures.consoleErrors.length, 4)
  assert.equal(failures.nonSuccessfulResponses.length, 4)
})

test("classifySmokeFailures rejects a foreign-origin profile 401", () => {
  const failures = classifySmokeFailures({
    allowUnauthenticatedProfileProbe: true,
    expectedOrigin: "http://localhost",
    consoleMessages: [
      {
        type: "error",
        text: "Failed to load resource: the server responded with a status of 401 (Unauthorized)",
        location: { url: "https://foreign.example/api/v1/users/me" },
      },
    ],
    networkResponses: [
      { method: "GET", url: "https://foreign.example/api/v1/users/me", status: 401 },
    ],
  })

  assert.equal(failures.consoleErrors.length, 1)
  assert.equal(failures.nonSuccessfulResponses.length, 1)
})

test("classifySmokeFailures retains profile console errors beyond matched network probes", () => {
  const profileConsoleError = {
    type: "error",
    text: "Failed to load resource: the server responded with a status of 401 (Unauthorized)",
    location: { url: "http://localhost/api/v1/users/me" },
  }
  const failures = classifySmokeFailures({
    allowUnauthenticatedProfileProbe: true,
    expectedOrigin: "http://localhost",
    consoleMessages: [profileConsoleError, { ...profileConsoleError }],
    networkResponses: [{ method: "GET", url: "http://localhost/api/v1/users/me", status: 401 }],
  })

  assert.equal(failures.consoleErrors.length, 1)
  assert.deepEqual(failures.nonSuccessfulResponses, [])
})
