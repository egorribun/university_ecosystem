import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

const specUrl = new URL("./events-tab-keyboard.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const headerUrl = new URL("../../src/features/events/components/EventsHeader.tsx", import.meta.url)
const listUrl = new URL("../../src/features/events/components/EventsList.tsx", import.meta.url)
const featureUrl = new URL("../../src/features/events/EventsFeature.tsx", import.meta.url)
const russianEventsUrl = new URL("../../src/i18n/locales/ru/events.json", import.meta.url)
const fixturesUrl = new URL("./fixtures.ts", import.meta.url)

test("live Events tabs prove the real keyboard and accessible selection contract", async () => {
  let spec
  try {
    spec = await readFile(specUrl, "utf8")
  } catch {
    assert.fail("the executable live Events keyboard scenario must exist")
  }

  const [config, header, list, feature, russianEvents, fixtures] = await Promise.all([
    readFile(configUrl, "utf8"),
    readFile(headerUrl, "utf8"),
    readFile(listUrl, "utf8"),
    readFile(featureUrl, "utf8"),
    readFile(russianEventsUrl, "utf8"),
    readFile(fixturesUrl, "utf8"),
  ])

  assert.match(header, /role="tablist"[\s\S]*?aria-label=\{t\("events:pageTitle"\)\}/u)
  assert.match(header, /\{ key: "active", labelKey: "events:tabs\.active" \}/u)
  assert.match(header, /\{ key: "archive", labelKey: "events:tabs\.archive" \}/u)
  assert.match(header, /\{ key: "my", labelKey: "events:tabs\.my" \}/u)
  assert.match(header, /\["ArrowLeft", "ArrowRight", "Home", "End"\]/u)
  assert.match(
    header,
    /event\.preventDefault\(\)[\s\S]*?onTabChange\(nextTab\.key\)[\s\S]*?nextButton\.focus\(\)/u
  )
  assert.match(
    header,
    /role="tab"[\s\S]*?aria-selected=\{tab === tabItem\.key\}[\s\S]*?tabIndex=\{tab === tabItem\.key \? 0 : -1\}/u
  )
  assert.match(header, /aria-controls="events-tabpanel"/u)
  assert.match(
    list,
    /role="tabpanel"[\s\S]*?id="events-tabpanel"[\s\S]*?aria-labelledby=\{`events-tab-\$\{tab\}`\}/u
  )
  assert.match(feature, /const tab = \(searchParams\.tab as EventTabKey\) \|\| "active"/u)
  assert.match(feature, /const setTab = useCallback\(\(v: string\) => handleURLChange\("tab", v\)/u)
  assert.match(russianEvents, /"active": "Актуальные"/u)
  assert.match(russianEvents, /"archive": "Прошедшие"/u)
  assert.match(russianEvents, /"my": "Мои события"/u)
  assert.match(fixtures, /export async function loginAs\(page: Page, role: Role\)/u)
  assert.match(fixtures, /student:\s*\{/u)

  assert.match(spec, /test\("Events status tabs are keyboard navigable"/u)
  assert.match(spec, /await loginAs\(page, "student"\)/u)
  assert.match(spec, /await page\.goto\("\/events"\)/u)
  assert.match(spec, /getByRole\("tablist",\s*\{\s*name: \/Мероприятия\|Events\/u\s*\}\)/u)
  for (const key of ["ArrowRight", "ArrowLeft", "Home", "End"]) {
    assert.match(spec, new RegExp(`page\\.keyboard\\.press\\(["']${key}["']\\)`, "u"))
  }
  assert.match(spec, /toHaveAttribute\("aria-selected", "true"\)/u)
  assert.match(spec, /toHaveAttribute\("tabindex", "0"\)/u)
  assert.match(spec, /toBeFocused\(\)/u)
  assert.match(spec, /toHaveAttribute\("aria-labelledby", `events-tab-\$\{selectedKey\}`\)/u)
  assert.match(spec, /searchParams\.get\("tab"\)/u)
  assert.doesNotMatch(spec, /test\.skip/u)
  assert.doesNotMatch(
    spec,
    /page\.route|routeWebSocket|page\.request\.(?:post|put|patch|delete)|localStorage\.setItem/u
  )

  assert.match(config, /testDir: "\.\/tests\/e2e-live"/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
  assert.match(config, /name: "desktop"/u)
  assert.match(config, /name: "mobile"/u)
})
