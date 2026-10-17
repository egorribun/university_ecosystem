import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import { URL } from "node:url"

const specUrl = new URL("./news-responsive-matrix.live.spec.ts", import.meta.url)
const fixtureUrl = new URL("./fixtures.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const planUrl = new URL("../../../docs/superpowers/plans/MVP_MASTER_PLAN.md", import.meta.url)
const newsHeaderUrl = new URL("../../src/features/news/components/NewsHeader.tsx", import.meta.url)
const englishNewsUrl = new URL("../../src/i18n/locales/en/news.json", import.meta.url)
const russianNewsUrl = new URL("../../src/i18n/locales/ru/news.json", import.meta.url)

test("real News content is checked in RU and EN across the approved width matrix", async () => {
  let spec
  try {
    spec = await readFile(specUrl, "utf8")
  } catch {
    assert.fail("the RU/EN News responsive acceptance scenario must exist")
  }

  const [fixtures, config, plan, newsHeader, englishNewsSource, russianNewsSource] =
    await Promise.all([
      readFile(fixtureUrl, "utf8"),
      readFile(configUrl, "utf8"),
      readFile(planUrl, "utf8"),
      readFile(newsHeaderUrl, "utf8"),
      readFile(englishNewsUrl, "utf8"),
      readFile(russianNewsUrl, "utf8"),
    ])

  assert.match(
    plan,
    /RU\/EN и ширины 390\/768\/1440 px обязательны; 360\/1024 px\s+проверять для меню, таблиц и рисковых адаптивных сценариев/u
  )
  assert.match(spec, /loginAs\(page, ["']student["']\)/u)
  assert.match(spec, /page\.goto\(["']\/news["']\)/u)
  assert.match(spec, /const WIDTHS\s*=\s*\[360,\s*390,\s*768,\s*1024,\s*1440\]/u)
  assert.match(spec, /language:\s*["']ru["']/u)
  assert.match(spec, /language:\s*["']en["']/u)
  assert.ok(spec.includes("listHeading: /^(?:University news|University news ?[0-9]+)$/u"))
  assert.ok(
    spec.includes("listHeading: /^(?:Новости университета|Новости университета ?[0-9]+)$/u")
  )
  assert.equal(JSON.parse(englishNewsSource).pageTitle, "University news")
  assert.equal(JSON.parse(russianNewsSource).pageTitle, "Новости университета")
  assert.match(newsHeader, /<h1[\s\S]*?t\("news:pageTitle"\)[\s\S]*?newsCount/u)
  assert.match(
    spec,
    /expect\.poll\(\(\) => new URL\(page\.url\(\)\)\.pathname\)\.toBe\(["']\/news["']\)/u
  )
  assert.match(spec, /page\.setViewportSize\(\{\s*width,\s*height:/u)
  assert.match(spec, /getByRole\(["']heading["'],\s*\{\s*name:\s*locale\.listHeading/u)
  assert.match(spec, /getByRole\(["']link["'],\s*\{\s*name:\s*locale\.articleTitle/u)
  assert.match(spec, /documentElement\.scrollWidth/u)
  assert.match(spec, /toBeLessThanOrEqual\(\s*width\s*\+\s*1\s*\)/u)
  assert.doesNotMatch(
    spec,
    /page\.route\(|routeFromHAR|useMockApi|page\.request\.(?:post|put|patch|delete)\(/u
  )
  assert.match(
    fixtures,
    /export async function loginAs\(\s*page: Page,\s*role: Role,\s*cleanupDeadlineAtMs\?: number,\s*maximumOperationTimeoutMs = LIVE_OWNED_CLEANUP_OPERATION_TIMEOUT_MS\s*\): Promise<void> \{\s*await loginWith\(\s*page,\s*ROLES\[role\]\.email,\s*ROLES\[role\]\.password,\s*cleanupDeadlineAtMs,\s*maximumOperationTimeoutMs\s*\)/u
  )
  assert.match(config, /name:\s*["']desktop["']/u)
  assert.match(config, /name:\s*["']mobile["']/u)
  assert.match(config, /trace:\s*["']off["']/u)
  assert.match(config, /screenshot:\s*["']off["']/u)
  assert.match(config, /video:\s*["']off["']/u)
})
