import assert from "node:assert/strict"
import { existsSync } from "node:fs"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"
import {
  isOpaqueRegistrationReceipt,
  waitForRegistrationCompletion,
  withRegistrationDetach,
} from "./register-double-submit-lifecycle.mjs"

const specUrl = new URL("./register-double-submit.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const registerUrl = new URL("../../src/pages/Register.tsx", import.meta.url)

test("live registration double-submit acceptance uses one real owned account", async () => {
  assert.equal(
    existsSync(specUrl),
    true,
    "the mobile double-submit registration acceptance must exist"
  )

  const [spec, config, register] = await Promise.all([
    readFile(specUrl, "utf8"),
    readFile(configUrl, "utf8"),
    readFile(registerUrl, "utf8"),
  ])

  assert.match(config, /name:\s*["']desktop["']/u)
  assert.match(config, /name:\s*["']mobile["']/u)
  assert.match(config, /trace:\s*["']off["']/u)
  assert.match(config, /screenshot:\s*["']off["']/u)
  assert.match(config, /video:\s*["']off["']/u)
  assert.match(register, /api\.post\(["']\/auth\/register["']/u)
  assert.match(register, /navigate\(\{\s*to:\s*["']\/login["']\s*\}\)/u)
  assert.match(register, /const \[hydrated, setHydrated\] = useState\(false\)/u)
  assert.match(register, /useEffect\(\(\) => \{\s*setHydrated\(true\)\s*\}, \[\]\)/u)
  assert.match(register, /const controlsDisabled = !hydrated \|\| isSubmitting\s*$/mu)

  // Bind the readiness/submission guard to actual controls, not an unrelated
  // disabled prop elsewhere in the component. Runtime hydration tests and the
  // live double-submit acceptance remain the behavioral evidence.
  const fieldControls = Array.from(
    register.matchAll(/<(?:Input|Select)\b[\s\S]*?\/>/gu),
    ([source]) => source
  )
  const buttonControls = Array.from(
    register.matchAll(/<(?:Button|button)\b[\s\S]*?^\s*>/gmu),
    ([source]) => source
  )
  assert.equal(fieldControls.length, 6, "five inputs, including invite code, and one role selector")
  assert.equal(buttonControls.length, 4, "submit, two reveal buttons, and the email suggestion")
  for (const control of [...fieldControls, ...buttonControls]) {
    assert.match(control, /disabled=\{controlsDisabled\}/u)
  }
  const submit = buttonControls.find((control) => /id=["']register-submit["']/u.test(control))
  assert.ok(submit, "the real registration submit control must exist")
  assert.match(submit, /type=["']submit["']/u)
  assert.match(submit, /loading=\{isSubmitting\}/u)

  assert.match(spec, /page\.setViewportSize\(\{\s*width:\s*360/u)
  assert.match(spec, /stubBreachedPasswordLookup\(page\)/u)
  const registrationNavigation = spec.indexOf(
    'await page.goto("/register", { waitUntil: "domcontentloaded" })'
  )
  const hydrationWait = spec.indexOf(
    "await page.waitForFunction(() => window.__APP_HYDRATED === true)",
    registrationNavigation
  )
  const firstFormInteraction = spec.indexOf('await page.locator("#full_name").fill')
  assert.ok(
    registrationNavigation >= 0 &&
      hydrationWait > registrationNavigation &&
      firstFormInteraction > hydrationWait,
    "registration controls must not be interacted with before React hydration"
  )
  assert.match(spec, /freshPassword\(\)/u)
  assert.match(
    spec,
    /createOwnedResetAccount\(testInfo\.project\.name,\s*crypto\.randomUUID\(\)\)/u
  )
  assert.match(spec, /touchscreen\.tap\(x,\s*y\)/u)
  assert.match(spec, /dblclick\(/u)
  assert.match(spec, /registerPostCount/u)
  assert.match(spec, /expect\(registerPostCount\)\.toBe\(1\)/u)
  assert.match(spec, /isOpaqueRegistrationReceipt\(registrationBody\)/u)
  assert.match(spec, /withRegistrationDetach\(/u)
  assert.doesNotMatch(spec, /registrationBody\?\.id|registrationBody\.id/u)
  assert.match(spec, /registerOwnedSessionCleanup\(/u)
  assert.match(spec, /findOwnedResetUserId\(/u)
  assert.match(spec, /readOwnedResetUserId\(/u)
  assert.match(spec, /await loginWith\(page, email, password\)/u)
  assert.match(spec, /method:\s*["']DELETE["']/u)
  const cleanupRegistration = spec.indexOf("registerOwnedSessionCleanup(")
  const requestListener = spec.indexOf('page.on("request", countRegistrationPosts)')
  const click = spec.indexOf("await submitButton.dblclick")
  assert.ok(
    cleanupRegistration >= 0 && cleanupRegistration < requestListener && requestListener < click,
    "the owned-account cleanup must be registered before a registration request can be sent"
  )
  assert.match(spec, /if \(!registrationSubmitAttempted && registerPostCount === 0\) return/u)
  assert.match(spec, /createdUser\.id \?\?\s*\(await findOwnedResetUserId\(/u)
  assert.match(spec, /section\.auth-shell--login/u)
  assert.ok(
    spec.lastIndexOf("no extra registration request during navigation and identity verification") >
      spec.indexOf("createdUser.id = await readOwnedResetUserId("),
    "the request-count observation continues through identity verification"
  )
  assert.match(
    spec,
    /expect\(\s*registerPostCount,\s*"no extra registration request during navigation and identity verification"\s*\)\.toBe\(1\)/u
  )
  assert.match(
    spec,
    /await page\.close\(\)[\s\S]*?expect\(\s*registerPostCount,\s*"no extra registration request before the page closed"\s*\)\.toBe\(1\)/u
  )
  assert.match(spec, /\/login\$/u)
  assert.doesNotMatch(
    spec,
    /page\.route|routeWebSocket|page\.request\.(?:post|put|patch|delete)\(|fulfill\(/u
  )
  assert.doesNotMatch(spec, /password\s*[:=]\s*["'][^"']+/iu)
})

test("registration accepts only the generic success receipt", () => {
  assert.equal(isOpaqueRegistrationReceipt({ status: "ok" }), true)
  for (const invalid of [
    null,
    undefined,
    [],
    "ok",
    {},
    { status: "error" },
    { status: "ok", id: "unexpected-public-identifier" },
  ]) {
    assert.equal(isOpaqueRegistrationReceipt(invalid), false)
  }
})

test("registration detaches after success and preserves the result", async () => {
  let detached = 0
  let reported = 0
  const result = await withRegistrationDetach(
    async () => "result",
    async () => {
      detached += 1
    },
    () => {
      reported += 1
    }
  )
  assert.equal(result, "result")
  assert.equal(detached, 1)
  assert.equal(reported, 0)
})

test("a detach failure does not mask a registration failure", async () => {
  const primary = new Error("registration failed")
  let reported = 0
  await assert.rejects(
    withRegistrationDetach(
      async () => {
        throw primary
      },
      async () => {
        throw new Error("private CDP details")
      },
      () => {
        reported += 1
      }
    ),
    (error) => error === primary
  )
  assert.equal(reported, 1)
})

test("a detach failure after success remains a failure without exposing CDP details", async () => {
  await assert.rejects(
    withRegistrationDetach(
      async () => "result",
      async () => {
        throw new Error("private CDP details")
      },
      () => {
        throw new Error("unused")
      }
    ),
    (error) =>
      error instanceof Error &&
      error.message === "Registration browser cleanup failed" &&
      !String(error).includes("private CDP details")
  )
})

test("a broken detach diagnostic cannot replace the registration failure", async () => {
  const primary = new Error("registration failed")
  let diagnostics = 0
  await assert.rejects(
    withRegistrationDetach(
      async () => {
        throw primary
      },
      async () => {
        throw new Error("private CDP details")
      },
      () => {
        diagnostics += 1
        throw new Error("diagnostic failed")
      }
    ),
    (error) => error === primary
  )
  assert.equal(diagnostics, 1)
})

test("registration cleanup waits for all observed request completions", async () => {
  let finish
  const pending = new Promise((resolve) => {
    finish = resolve
  })
  let settled = false
  const result = waitForRegistrationCompletion([Promise.resolve(true), pending], 500).then(
    (value) => {
      settled = true
      return value
    }
  )
  await new Promise((resolve) => globalThis.setImmediate(resolve))
  assert.equal(settled, false)
  finish(true)
  assert.equal(await result, true)
})

test("failed or missing request completion remains unverified", async () => {
  assert.equal(await waitForRegistrationCompletion([], 100), false)
  assert.equal(await waitForRegistrationCompletion([Promise.resolve(true)], 0), false)
  assert.equal(await waitForRegistrationCompletion([Promise.resolve(false)], 100), false)
  const failedRequest = Promise.reject(new Error("private transport"))
  void failedRequest.catch(() => undefined)
  assert.equal(await waitForRegistrationCompletion([failedRequest], 100), false)
  assert.equal(await waitForRegistrationCompletion([new Promise(() => {})], 10), false)
})
