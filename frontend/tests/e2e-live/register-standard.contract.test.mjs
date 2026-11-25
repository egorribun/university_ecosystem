import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { randomUUID } from "node:crypto"
import { URL } from "node:url"
import test from "node:test"
import { runInNewContext } from "node:vm"
import typescript from "typescript"
import {
  isOpaqueRegistrationReceipt,
  waitForRegistrationCompletion,
  withRegistrationDetach,
} from "./register-double-submit-lifecycle.mjs"

const specUrl = new URL("./register-standard.live.spec.ts", import.meta.url)
const origin = "http://127.0.0.1:20000"
const ownedId = "c3db1691-f951-42e8-a5df-ffb970f6a2be"
const expectedCases = [
  [390, "ru"],
  [768, "ru"],
  [1440, "ru"],
  [390, "en"],
  [768, "en"],
  [1440, "en"],
]

async function scenario(options = {}) {
  const source = await readFile(specUrl, "utf8")
  const compiled = typescript.transpileModule(source, {
    compilerOptions: {
      module: typescript.ModuleKind.CommonJS,
      target: typescript.ScriptTarget.ES2022,
    },
  }).outputText
  const declarations = new Map()
  const events = []
  const fields = new Map()
  const account = { email: "owned@example.invalid", fullName: "Owned Student" }
  let cleanup
  let onRequest
  let responsePredicate
  let resolveResponse
  let closed = false
  let viewportWidth
  let language
  const response = {
    request: () => request,
    status: () => options.status ?? 200,
    json: async () => (options.invalidReceipt ? { status: "unexpected" } : { status: "ok" }),
    finished: async () => (options.unfinished ? new Error("incomplete") : null),
  }
  const request = {
    method: () => "POST",
    url: () => `${origin}/api/v1/auth/register`,
    response: async () => response,
  }
  const page = {
    url: "/register",
    setViewportSize: async ({ width }) => {
      viewportWidth = width
      events.push("viewport")
    },
    emulateMedia: async () => {},
    addInitScript: async (_fn, locale) => {
      assert.equal(locale, language)
    },
    goto: async () => {},
    waitForFunction: async () => {},
    getByRole: (_role, { name }) => ({ kind: "heading", name }),
    locator: (selector) => ({
      selector,
      fill: async (value) => fields.set(selector, value),
      scrollIntoViewIfNeeded: async () => {},
      click: async () => {
        events.push("click")
        assert.ok(cleanup, "cleanup must be registered before submit")
        if (options.clickFailure) throw new Error("click interrupted")
        onRequest(request)
        if (options.duplicate) onRequest(request)
        assert.equal(responsePredicate(response), true)
        resolveResponse(response)
        page.url = "/login"
      },
    }),
    evaluate: async () => viewportWidth,
    on: (_event, listener) => {
      onRequest = listener
    },
    off: () => {
      onRequest = undefined
    },
    waitForResponse: (predicate) =>
      new Promise((resolve) => {
        responsePredicate = predicate
        resolveResponse = resolve
      }),
    isClosed: () => closed,
    close: async () => {
      closed = true
      events.push("registration-page-closed")
    },
  }
  const identityPage = {
    request: { kind: "identity" },
    addInitScript: async () => events.push("identity-locale"),
    close: async () => events.push("identity-page-closed"),
  }
  const context = {
    addCookies: async ([cookie]) => {
      language = cookie.value
      events.push(`locale:${language}`)
    },
    newPage: async () => identityPage,
  }
  const adminPage = {
    request: { kind: "admin" },
    evaluate: async (_callback, input) => {
      events.push(["delete", input.userId])
      return options.deleteFailure
        ? { status: 500, deleted: false }
        : { status: 200, deleted: true }
    },
  }
  const cleanupBrowser = {
    newContext: async () => ({
      newPage: async () => adminPage,
      close: async () => events.push("cleanup-context-closed"),
    }),
  }
  const fixtures = {
    test: (title, callback) => declarations.set(title, callback),
    expect: (actual) => ({
      toBe: (expected) => assert.equal(actual, expected),
      toHaveAttribute: async (attribute, expected) => {
        assert.equal(attribute, "lang")
        assert.equal(language, expected)
      },
      toHaveText: async (expected) =>
        assert.equal(expected, language === "ru" ? "Студент" : "Student"),
      toBeVisible: async () => {},
      toBeEnabled: async () => {},
      toHaveURL: async (pattern) => assert.match(actual.url, pattern),
    }),
    freshPassword: () => "p".repeat(24),
    liveDeadlineBoundedTimeoutMs: () => 5_000,
    liveTestSlotDeadlineAtMs: () => 20_000,
    loginAs: async () => events.push("admin-login"),
    loginWith: async () => {
      events.push("identity-login")
      if (options.identityFailure) throw new Error("identity unavailable")
    },
    ownedSessionOrigin: () => origin,
    registerOwnedSessionCleanup: (callback) => {
      events.push("cleanup-registered")
      cleanup = callback
    },
    stubBreachedPasswordLookup: async () => events.push("breach-stub"),
    withLiveRegistrationAdmission: async (_page, cost, action) => {
      events.push(["admission", cost])
      if (options.admissionFailure) throw new Error("admission unavailable")
      return action()
    },
  }
  const identity = {
    createOwnedResetAccount: (project, nonce) => {
      assert.equal(project, "desktop")
      assert.match(nonce, /^[0-9a-f-]{36}$/u)
      return account
    },
    findOwnedResetUserId: async (_api, actualOrigin, actualAccount) => {
      events.push("fallback-identity")
      assert.equal(actualOrigin, origin)
      assert.equal(actualAccount, account)
      return ownedId
    },
    readOwnedResetUserId: async (_api, actualOrigin, actualAccount) => {
      events.push("verified-identity")
      assert.equal(actualOrigin, origin)
      assert.equal(actualAccount, account)
      return ownedId
    },
  }
  const modules = {
    "node:crypto": { randomUUID },
    "./fixtures": fixtures,
    "./password-reset-account-identity": identity,
    "./register-double-submit-lifecycle.mjs": {
      isOpaqueRegistrationReceipt,
      waitForRegistrationCompletion,
      withRegistrationDetach,
    },
  }
  runInNewContext(compiled, {
    exports: {},
    require: (name) => {
      assert.ok(Object.hasOwn(modules, name), `unexpected module ${name}`)
      return modules[name]
    },
    process: { env: { LIVE_BASE_URL: origin } },
    URL,
  })
  const invoke = async (title) =>
    declarations.get(title)({ page, context }, { project: { name: "desktop" }, annotations: [] })
  const finish = async () => cleanup(cleanupBrowser, 20_000)
  return { declarations, events, fields, invoke, finish, source }
}

test("six literal scenarios use the owned single-submit path", async () => {
  for (const [width, locale] of expectedCases) {
    const run = await scenario()
    const title = `ordinary registration at ${width}px in ${locale.toUpperCase()}`
    assert.equal(run.declarations.size, 6)
    await run.invoke(title)
    await run.finish()
    assert.equal(run.events.filter((event) => event === "click").length, 1)
    assert.ok(run.events.indexOf("cleanup-registered") < run.events.indexOf("click"))
    assert.ok(run.events.indexOf("breach-stub") < run.events.indexOf("click"))
    assert.ok(run.events.includes(`locale:${locale}`))
    assert.deepEqual(run.events.filter(Array.isArray), [
      ["admission", 1],
      ["delete", ownedId],
    ])
    assert.ok(run.events.includes("verified-identity"))
    assert.ok(run.events.includes("registration-page-closed"))
    assert.equal(run.fields.get("#email"), "owned@example.invalid")
    assert.doesNotMatch(
      run.source,
      /page\.route|routeWebSocket|page\.request\.(?:post|put|patch|delete)\(|fulfill\(/u
    )
  }
})

test("an admission refusal closes the page without creating or deleting an account", async () => {
  const run = await scenario({ admissionFailure: true })
  await assert.rejects(run.invoke("ordinary registration at 390px in RU"), /admission unavailable/u)
  await run.finish()
  assert.equal(run.events.includes("click"), false)
  assert.equal(run.events.includes("admin-login"), false)
  assert.ok(run.events.includes("registration-page-closed"))
})

test("a failed response, receipt or identity check deletes only the exact owned account", async () => {
  for (const options of [{ status: 500 }, { invalidReceipt: true }, { identityFailure: true }]) {
    const run = await scenario(options)
    await assert.rejects(run.invoke("ordinary registration at 768px in EN"))
    await run.finish()
    assert.ok(run.events.includes("fallback-identity"))
    assert.deepEqual(run.events.filter(Array.isArray), [
      ["admission", 1],
      ["delete", ownedId],
    ])
  }
})

test("an uncertain click still attempts exact deletion and fails closed", async () => {
  const run = await scenario({ clickFailure: true })
  await assert.rejects(run.invoke("ordinary registration at 390px in RU"), /click interrupted/u)
  await assert.rejects(run.finish(), /request completion could not be verified/u)
  assert.deepEqual(run.events.filter(Array.isArray), [
    ["admission", 1],
    ["delete", ownedId],
  ])
  assert.ok(run.events.includes("fallback-identity"))
})

test("an unconfirmed request is deleted but cannot report cleanup success", async () => {
  const run = await scenario({ unfinished: true })
  await run.invoke("ordinary registration at 1440px in RU")
  await assert.rejects(run.finish(), /request completion could not be verified/u)
  assert.deepEqual(run.events.filter(Array.isArray), [
    ["admission", 1],
    ["delete", ownedId],
  ])
})

test("an unverified delete cannot report cleanup success", async () => {
  const run = await scenario({ deleteFailure: true })
  await run.invoke("ordinary registration at 768px in RU")
  await assert.rejects(run.finish(), /account cleanup could not be verified/u)
})

test("a duplicate POST cannot pass the ordinary submission scenario", async () => {
  const run = await scenario({ duplicate: true })
  await assert.rejects(run.invoke("ordinary registration at 390px in EN"))
  await run.finish()
  assert.equal(run.events.filter((event) => event === "click").length, 1)
  assert.ok(run.events.includes("fallback-identity"))
})
