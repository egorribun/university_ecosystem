import assert from "node:assert/strict"
import { randomUUID } from "node:crypto"
import { readFile } from "node:fs/promises"
import { fileURLToPath, URL } from "node:url"
import test from "node:test"
import { runInThisContext } from "node:vm"
import typescript from "typescript"

const specUrl = new URL("./auth-safe-redirect.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const [spec, config] = await Promise.all([readFile(specUrl, "utf8"), readFile(configUrl, "utf8")])
const compiled = typescript.transpileModule(spec, {
  compilerOptions: {
    module: typescript.ModuleKind.CommonJS,
    target: typescript.ScriptTarget.ES2022,
  },
}).outputText

const origin = "https://owned.example.invalid"
const cases = [
  ["an absolute external URL", "https://redirect-target.invalid/landing"],
  ["a protocol-relative URL", "//redirect-target.invalid/landing"],
  [
    "a slash-backslash URL normalized as an external URL by browsers",
    "/\\redirect-target.invalid/landing",
  ],
]

// Execute the registered live callbacks against a controlled page; this proves
// their wiring and assertions, not a live backend or browser's redirect behavior.
function scenario(
  index,
  { destination = `${origin}/dashboard`, stripQuery = false, afterUrlCheck } = {}
) {
  const student = { email: "student@example.invalid", password: randomUUID() }
  const events = []
  const callbacks = []
  let currentUrl
  const email = {
    async fill(value) {
      events.push(["fill", "email", value])
    },
  }
  const password = {
    async fill(value) {
      events.push(["fill", "password", value])
    },
  }
  const submit = {
    async click() {
      events.push(["click", "login"])
      currentUrl = destination
    },
  }
  const page = {
    async goto(path) {
      events.push(["goto", path])
      const url = new URL(path, origin)
      if (stripQuery) url.searchParams.delete("redirect")
      currentUrl = url.href
    },
    url: () => currentUrl,
    getByRole(role, options) {
      if (role === "textbox") {
        assert.deepEqual(options, { name: "E-mail" })
        return email
      }
      assert.equal(role, "button")
      assert.deepEqual(options, { name: "Войти" })
      return submit
    },
    getByLabel(name, options) {
      assert.equal(name, "Пароль")
      assert.deepEqual(options, { exact: true })
      return password
    },
  }
  function fakeExpect(actual) {
    return {
      toBe(expected) {
        events.push(["equal", actual, expected])
        assert.equal(actual, expected)
      },
      async toBeVisible() {
        assert.equal(actual, email)
        events.push(["visible", "email"])
      },
      async toHaveURL(expected) {
        assert.equal(actual, page)
        events.push(["url", page.url(), expected])
        assert.equal(page.url(), expected)
        if (afterUrlCheck) currentUrl = afterUrlCheck
      },
    }
  }
  const fixture = {
    expect: fakeExpect,
    ROLES: { student },
    test(name, callback) {
      callbacks.push({ name, callback })
    },
  }
  const load = runInThisContext(`(function(exports, require) {\n${compiled}\n})`, {
    filename: fileURLToPath(specUrl),
  })
  load({}, (id) => {
    assert.equal(id, "./fixtures", `unexpected scenario dependency: ${id}`)
    return fixture
  })
  assert.deepEqual(
    callbacks.map(({ name }) => name),
    cases.map(([label]) => `seeded login keeps ${label} on the same origin`)
  )
  return { events, student, run: () => callbacks[index].callback({ page }) }
}

test("safe-redirect config and no-mock policy guards remain in place", () => {
  assert.match(config, /testDir:\s*["']\.\/tests\/e2e-live["']/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
  assert.doesNotMatch(
    spec,
    /\b(?:loginAs|loginWith|submitLogin)\s*\(/u,
    "the redirect query must survive until the actual login form submits"
  )
  assert.doesNotMatch(
    spec,
    /page\.route|routeWebSocket|useMockApi|vi\.mock|page\.request/u,
    "the live safe-redirect check must use the real backend without network mocks"
  )
})

test("each live callback submits the seeded form and checks its hostile target and landing", async () => {
  for (const [index, [, target]] of cases.entries()) {
    const { events, student, run } = scenario(index)
    await run()
    assert.deepEqual(events, [
      ["goto", `/login?redirect=${encodeURIComponent(target)}`],
      ["equal", "/login", "/login"],
      ["equal", target, target],
      ["visible", "email"],
      ["fill", "email", student.email],
      ["fill", "password", student.password],
      ["click", "login"],
      ["url", `${origin}/dashboard`, `${origin}/dashboard`],
      ["equal", origin, origin],
    ])
  }
})

test("each live callback rejects a lost query, wrong landing, and subsequent origin escape", async () => {
  for (const [index, [, target]] of cases.entries()) {
    await assert.rejects(scenario(index, { stripQuery: true }).run(), {
      name: "AssertionError",
      actual: null,
      expected: target,
    })
    await assert.rejects(scenario(index, { destination: `${origin}/profile` }).run(), {
      name: "AssertionError",
      actual: `${origin}/profile`,
      expected: `${origin}/dashboard`,
    })
    await assert.rejects(
      scenario(index, { destination: "https://redirect-target.invalid/landing" }).run(),
      {
        name: "AssertionError",
        actual: "https://redirect-target.invalid/landing",
        expected: `${origin}/dashboard`,
      }
    )
    await assert.rejects(
      scenario(index, { afterUrlCheck: "https://redirect-target.invalid/landing" }).run(),
      {
        name: "AssertionError",
        actual: "https://redirect-target.invalid",
        expected: origin,
      }
    )
  }
})
