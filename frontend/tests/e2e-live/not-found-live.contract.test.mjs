import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

const specUrl = new URL("./not-found-i18n.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const [spec, config] = await Promise.all([readFile(specUrl, "utf8"), readFile(configUrl, "utf8")])

test("live unknown-path acceptance checks the 404 shell after static i18n initialization", () => {
  assert.match(config, /testDir:\s*["']\.\/tests\/e2e-live["']/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
  assert.match(spec, /page\.goto\("\/__live-e2e-missing-route-404__"\)/u)
  assert.match(spec, /response\?\.status\(\)\)\.toBe\(404\)/u)
  assert.match(spec, /data-not-found-page/u)
  assert.match(spec, /document\.readyState/u)
  assert.match(spec, /not-found-i18n\.js/u)
  assert.match(spec, /Страница не найдена/u)
  assert.match(spec, /data-i18n/u)
  assert.match(spec, /unsafeRequests/u)
  assert.match(spec, /expect\(unsafeRequests\)\.toEqual\(\[\]\)/u)

  assert.doesNotMatch(
    spec,
    /page\.route|routeWebSocket|useMockApi|vi\.mock|page\.request|loginAs/u,
    "the public not-found live check must use the real, read-only document path"
  )
})

test("English browser locale is checked after the static not-found translator runs", () => {
  const englishTestStart = spec.indexOf(
    'test("English browser resolves localized 404 content after initialization"'
  )
  assert.notEqual(englishTestStart, -1, "the live 404 acceptance must cover English")
  const englishSpec = spec.slice(englishTestStart)

  assert.ok(
    /locale:\s*["']en-US["']/u.test(englishSpec),
    "the English case must use an English browser locale"
  )
  assert.match(englishSpec, /Page not found/u)
  assert.match(englishSpec, /Page not found — GUU Ecosystem/u)
  assert.match(englishSpec, /response!?\.text\(\)/u)
  assert.match(englishSpec, /<html lang="ru" data-not-found-page>/u)
  assert.match(englishSpec, /Страница не найдена — Экосистема ГУУ/u)
  assert.match(englishSpec, /notFound\.title/u)
  assert.match(englishSpec, /notFound\.description/u)
  assert.match(englishSpec, /serverHtml\)\.not\.toMatch/u)
  assert.match(englishSpec, /not-found-i18n\.js/u)
  assert.match(englishSpec, /querySelectorAll<HTMLElement>/u)
  assert.match(englishSpec, /data-i18n/u)
  assert.match(englishSpec, /expect\(state\.translations\)\.toHaveLength\(4\)/u)
  assert.match(englishSpec, /text\)\.not\.toBe\(key\)/u)
})

test("both localized 404 browser documents exclude technical error output", () => {
  assert.match(
    spec,
    /async function assertNoTechnicalErrorText\(page: Page\)[\s\S]*?Internal Server Error[\s\S]*?Traceback/u
  )
  assert.equal(
    (spec.match(/await assertNoTechnicalErrorText\(page\)/gu) ?? []).length,
    2,
    "Russian and English 404 flows must both check visible output"
  )
})
