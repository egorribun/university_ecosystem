import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import process from "node:process"
import { after, before, test } from "node:test"
import { URL } from "node:url"

import { parse } from "@babel/parser"
import { chromium } from "playwright"

const specUrl = new URL("./profile-csrf.live.spec.ts", import.meta.url)
const origin = "http://127.0.0.1:41799"
const csrfToken = "synthetic-csrf-token"
const candidateName = "Synthetic CSRF profile"

// Execute the callback from the live spec itself, so this check cannot pass by
// testing a second implementation of the cookie observation.
const findNodes = (node, predicate) => {
  if (!node || typeof node !== "object") return []
  if (Array.isArray(node)) return node.flatMap((entry) => findNodes(entry, predicate))
  return [
    ...(predicate(node) ? [node] : []),
    ...Object.values(node).flatMap((entry) => findNodes(entry, predicate)),
  ]
}

const readCallbacks = async () => {
  const source = await readFile(specUrl, "utf8")
  const syntax = parse(source, { sourceType: "module", plugins: ["typescript"] })
  const attempts = findNodes(
    syntax,
    (node) => node.type === "VariableDeclarator" && node.id?.name === "invalidCsrfAttempt"
  )
  assert.equal(attempts.length, 1, "the live spec has one invalid CSRF attempt")
  const evaluation = attempts[0].init?.argument
  assert.equal(evaluation?.type, "CallExpression")
  assert.equal(evaluation.callee?.object?.name, "page")
  assert.equal(evaluation.callee?.property?.name, "evaluate")
  const callback = evaluation.arguments[0]
  assert.equal(callback?.type, "ArrowFunctionExpression")
  assert.equal(callback.body?.type, "BlockStatement")

  const statements = callback.body.body
  const observationIndex = statements.findIndex(
    (statement) =>
      statement.type === "VariableDeclaration" &&
      statement.declarations.some(
        (declaration) => declaration.id?.name === "cookieAfterInvalidProofResponse"
      )
  )
  assert.ok(observationIndex >= 0, "the invalid-signature 403 has a cookie observation")
  const observation = statements[observationIndex]
  const cleanup = statements[observationIndex + 1]
  assert.equal(cleanup?.type, "ExpressionStatement")
  assert.equal(cleanup.expression?.type, "AssignmentExpression")
  assert.equal(cleanup.expression.left?.object?.name, "document")
  assert.equal(cleanup.expression.left?.property?.name, "cookie")

  const callbackSource = source.slice(callback.start, callback.end)
  // Recreate the original regression in memory only. The negative control must
  // show why deleting the response cookie before reading it is a false pass.
  const reordered =
    source.slice(callback.start, observation.start) +
    source.slice(cleanup.start, cleanup.end) +
    source.slice(observation.end, cleanup.start) +
    source.slice(observation.start, observation.end) +
    source.slice(cleanup.end, callback.end)
  return { callbackSource, reordered }
}

let browser
let callbacks

before(async () => {
  callbacks = await readCallbacks()
  const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
  browser = await chromium.launch(executablePath ? { executablePath } : {})
})

after(async () => {
  await browser?.close()
})

const observe = async (callbackSource, setCookieOnRequest = null) => {
  const context = await browser.newContext()
  const requests = []
  try {
    await context.route("**/*", async (route) => {
      const request = route.request()
      const url = new URL(request.url())
      if (url.origin === origin && url.pathname === "/" && request.method() === "GET") {
        await route.fulfill({ status: 200, contentType: "text/html", body: "<title>CSRF</title>" })
        return
      }
      if (
        url.origin === origin &&
        url.pathname === "/api/v1/users/me" &&
        request.method() === "PUT"
      ) {
        requests.push({ headers: await request.allHeaders(), body: request.postDataJSON() })
        await route.fulfill({
          status: 403,
          headers:
            setCookieOnRequest === requests.length
              ? { "set-cookie": "csrf_token=response-cookie; Path=/; SameSite=Lax" }
              : {},
          body: "rejected",
        })
        return
      }
      await route.abort()
    })
    const page = await context.newPage()
    await page.goto(`${origin}/`)
    await context.addCookies([
      { name: "csrf_token", value: csrfToken, url: origin },
      { name: "access_token_v2", value: "synthetic-session", url: origin, httpOnly: true },
    ])
    const observation = await page.evaluate(`(${callbackSource})(${JSON.stringify(candidateName)})`)

    assert.equal(requests.length, 2)
    assert.equal(requests[0].headers["x-csrf-token"], `${csrfToken}.invalid`)
    assert.match(
      requests[0].headers.cookie,
      /(?:^|; )csrf_token=synthetic-csrf-token\.invalid(?:;|$)/u
    )
    assert.equal(requests[1].headers["x-csrf-token"], csrfToken)
    assert.doesNotMatch(requests[1].headers.cookie ?? "", /(?:^|; )csrf_token=/u)
    for (const request of requests) {
      assert.match(request.headers.cookie, /(?:^|; )access_token_v2=synthetic-session(?:;|$)/u)
    }
    assert.deepEqual(
      requests.map((request) => request.body),
      [{ full_name: candidateName }, { full_name: candidateName }]
    )
    assert.equal(observation.status, 403)
    assert.equal(observation.proofMatchesCookie, true)
    assert.equal(observation.missingCookieAbsent, true)
    assert.equal(observation.missingCookieStatus, 403)
    const cookiesAfterCleanup = await context.cookies()
    assert.equal(
      cookiesAfterCleanup.some((cookie) => cookie.name === "csrf_token"),
      false
    )
    assert.equal(
      cookiesAfterCleanup.some((cookie) => cookie.name === "access_token_v2"),
      true
    )
    return observation
  } finally {
    await context.close()
  }
}

test("invalid-signature rejection preserves the submitted cookie when no response cookie is set", async () => {
  const observation = await observe(callbacks.callbackSource)
  assert.equal(observation.invalidProofCookiePresentAfterRejectedRequest, true)
  assert.equal(observation.invalidProofCookieMatchesSubmittedProof, true)
  assert.equal(observation.cookieClearedAfterRejectedRequest, true)
})

test("invalid-signature 403 observation detects a replacement cookie before cleanup", async () => {
  const observation = await observe(callbacks.callbackSource, 1)
  assert.equal(observation.invalidProofCookiePresentAfterRejectedRequest, true)
  assert.equal(observation.invalidProofCookieMatchesSubmittedProof, false)
})

test("cleanup before first-response observation recreates the false no-cookie result", async () => {
  const observation = await observe(callbacks.reordered, 1)
  assert.equal(observation.invalidProofCookiePresentAfterRejectedRequest, false)
  assert.equal(observation.invalidProofCookieMatchesSubmittedProof, false)
  assert.equal(observation.cookieClearedAfterRejectedRequest, true)
})

test("missing-cookie 403 observation detects a cookie before cleanup", async () => {
  const observation = await observe(callbacks.callbackSource, 2)
  assert.equal(observation.cookieClearedAfterRejectedRequest, false)
})
