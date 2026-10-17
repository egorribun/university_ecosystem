import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

const specUrl = new URL("./auth-safe-redirect.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const [spec, config] = await Promise.all([readFile(specUrl, "utf8"), readFile(configUrl, "utf8")])

test("safe-redirect live acceptance submits the real login form with hostile query intact", () => {
  assert.match(config, /testDir:\s*["']\.\/tests\/e2e-live["']/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
  assert.match(spec, /https:\/\/redirect-target\.invalid/u)
  assert.match(spec, /\/\/redirect-target\.invalid/u)
  assert.ok(
    spec.includes('target: "/\\\\redirect-target.invalid/landing"'),
    "live acceptance must include the browser-normalized slash-backslash open-redirect form"
  )
  assert.match(spec, /page\.goto\(`\/login\?redirect=\$\{encodeURIComponent\(target\)\}`\)/u)
  assert.match(spec, /loginUrl\.searchParams\.get\("redirect"\)/u)
  assert.match(spec, /ROLES\.student\.email/u)
  assert.match(spec, /ROLES\.student\.password/u)
  assert.match(spec, /getByRole\("textbox", \{ name: "E-mail" \}\)\.fill/u)
  assert.match(spec, /getByLabel\("Пароль", \{ exact: true \}\)\.fill/u)
  assert.match(spec, /getByRole\("button", \{ name: "Войти" \}\)\.click/u)
  assert.match(spec, /expect\(new URL\(page\.url\(\)\)\.origin\)\.toBe\(loginUrl\.origin\)/u)
  assert.match(spec, /toHaveURL\(new URL\("\/dashboard", loginUrl\.origin\)\.href\)/u)

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
