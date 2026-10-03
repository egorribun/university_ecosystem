import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import { URL } from "node:url"

const specUrl = new URL("./events-scroll-restoration.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const seedUrl = new URL("../../../scripts/seed_demo_data.py", import.meta.url)
const packageUrl = new URL("../../package.json", import.meta.url)
const featureUrl = new URL("../../src/features/events/EventsFeature.tsx", import.meta.url)
const cardUrl = new URL(
  "../../src/components/events/EventCard/EventCardContent.tsx",
  import.meta.url
)
const detailHeaderUrl = new URL(
  "../../src/components/events/EventDetailHeader.tsx",
  import.meta.url
)
const routeUrl = new URL("../../src/routes/_auth/events.$id.tsx", import.meta.url)
const appearanceUrl = new URL(
  "../../src/pages/settings/sections/AppearanceSection.tsx",
  import.meta.url
)
const englishEventsUrl = new URL("../../src/i18n/locales/en/events.json", import.meta.url)
const russianEventsUrl = new URL("../../src/i18n/locales/ru/events.json", import.meta.url)
const repositoryUrl = new URL("../../../app/repositories/event_repository.py", import.meta.url)

const [
  spec,
  config,
  seed,
  packageJson,
  feature,
  card,
  detailHeader,
  detailRoute,
  appearance,
  englishEventsSource,
  russianEventsSource,
  repository,
] = await Promise.all([
  readFile(specUrl, "utf8"),
  readFile(configUrl, "utf8"),
  readFile(seedUrl, "utf8"),
  readFile(packageUrl, "utf8"),
  readFile(featureUrl, "utf8"),
  readFile(cardUrl, "utf8"),
  readFile(detailHeaderUrl, "utf8"),
  readFile(routeUrl, "utf8"),
  readFile(appearanceUrl, "utf8"),
  readFile(englishEventsUrl, "utf8"),
  readFile(russianEventsUrl, "utf8"),
  readFile(repositoryUrl, "utf8"),
])

test("live Events history acceptance covers the seeded archive in RU and EN", () => {
  const eventSeedStart = seed.indexOf('"title": "Выпускной вечер 2026"')
  const eventSeedEnd = seed.indexOf("\n]\n", eventSeedStart)
  assert.ok(eventSeedStart >= 0 && eventSeedEnd > eventSeedStart)
  const seededEvent = seed.slice(eventSeedStart, eventSeedEnd)
  assert.match(seededEvent, /"starts_at": _dt\(2026, 6, 28/u)
  assert.match(seededEvent, /"ends_at": _dt\(2026, 6, 28/u)
  assert.match(seed, /"title": "Class of 2026 graduation ceremony"/u)

  const englishEvents = JSON.parse(englishEventsSource)
  const russianEvents = JSON.parse(russianEventsSource)
  assert.equal(englishEvents.pageTitle, "Events")
  assert.equal(englishEvents.tabs.archive, "Past events")
  assert.equal(russianEvents.pageTitle, "Мероприятия")
  assert.equal(russianEvents.tabs.archive, "Прошедшие")
  assert.match(feature, /tab === "archive" \? false/u)
  assert.match(repository, /if is_active is False:[\s\S]*?Event\.ends_at < now/u)

  assert.match(appearance, /name="language"/u)
  assert.match(appearance, /setLanguage\(value as SupportedLanguage\)/u)
  assert.match(card, /to="\/events\/\$id"[\s\S]*?params=\{\{ id \}\}/u)
  assert.match(detailRoute, /createFileRoute\("\/_auth\/events\/\$id"\)/u)
  assert.match(detailHeader, /<h1[\s\S]*?>\{title\}<\/h1>/u)

  assert.match(spec, /const LANGUAGE_KEY = "ue:language"/u)
  assert.match(spec, /const EVENT_LOCALES = \[/u)
  assert.match(spec, /code: "ru"/u)
  assert.match(spec, /languageOption: \/Русский\|Russian/u)
  assert.match(spec, /eventTitle: \/Выпускной вечер 2026/u)
  assert.match(spec, /code: "en"/u)
  assert.match(spec, /languageOption: \/Английский\|English/u)
  assert.match(spec, /eventTitle: \/Class of 2026 graduation ceremony/u)
  assert.match(spec, /async function selectLanguageThroughSettings/u)
  assert.match(spec, /getByRole\("radio", \{ name: locale\.languageOption \}\)/u)
  assert.match(spec, /await page\.reload\(\)/u)
  assert.match(spec, /localStorage\.getItem\(key\), LANGUAGE_KEY/u)
  assert.match(spec, /page\.evaluate\(\(\) => document\.cookie\)/u)
  assert.match(spec, /toHaveAttribute\("lang", locale\.code\)/u)

  const persistenceSection = spec.slice(
    spec.indexOf("async function verifyLanguagePersistsAfterReload"),
    spec.indexOf("async function verifyEventsHistoryForLanguage")
  )
  assert.match(persistenceSection, /await page\.reload\(\)/u)
  assert.match(persistenceSection, /toHaveAttribute\("lang", locale\.code\)/u)
  assert.match(persistenceSection, /localStorage\.getItem\(key\), LANGUAGE_KEY/u)
  assert.match(persistenceSection, /document\.cookie[\s\S]*?ue:language/u)
  assert.match(
    persistenceSection,
    /getByRole\("radio", \{ name: locale\.languageOption \}\)\)\.toBeChecked\(\)/u
  )

  const eventsAcceptance = spec.slice(
    spec.indexOf("async function verifyEventsHistoryForLanguage"),
    spec.indexOf("for (const locale of EVENT_LOCALES)")
  )
  const navigationStart = eventsAcceptance.indexOf('await page.goto("/events")')
  assert.ok(navigationStart > 0, "locale persistence must be asserted before opening Events")
  const beforeNavigation = eventsAcceptance.slice(0, navigationStart)
  assert.match(
    beforeNavigation,
    /getByRole\("radio", \{ name: locale\.languageOption \}\)\)\.toBeChecked\(\)/u
  )
  assert.match(beforeNavigation, /localStorage\.getItem\(key\), LANGUAGE_KEY/u)
  assert.match(beforeNavigation, /document\.cookie[\s\S]*?ue:language/u)

  assert.match(spec, /await loginAs\(page, "student"\)/u)
  assert.match(spec, /getByRole\("tab", \{ name: locale\.archiveTab \}\)/u)
  assert.match(spec, /getByRole\("link", \{ name: locale\.eventTitle \}\)/u)
  assert.match(spec, /await page\.goBack\(\)/u)
  assert.match(spec, /await page\.goForward\(\)/u)
  const browserForward = spec.slice(spec.indexOf("await page.goForward()"))
  assert.match(browserForward, /originalDetailPosition\.scrollY/u)
  assert.match(browserForward, /originalDetailPosition\.top/u)
  const finalBack = spec.slice(spec.lastIndexOf("await page.goBack()"))
  assert.match(finalBack, /restoredEventAfterForward/u)
  assert.match(finalBack, /originalPosition\.top/u)
  assert.equal(
    spec.match(
      /await page\.goBack\(\)\s+await expect\(page\)\.toHaveURL\(archiveUrl\)\s+await expect\(archiveTab\)\.toHaveAttribute\("aria-selected", "true"\)/gu
    )?.length,
    2,
    "both Back navigations must restore the accessible Archive tab state"
  )
  assert.match(spec, /selectedUrl\.href/u)
  assert.match(spec, /originalPosition\.scrollY/u)
  assert.match(spec, /originalPosition\.top/u)
  assert.match(
    spec,
    /test\(`browser history restores the Events archive position in \$\{locale\.code\}`/u
  )
  assert.match(spec, /verifyLanguagePersistsAfterReload\(page, locale\)/u)
  assert.match(spec, /verifyEventsHistoryForLanguage\(page, locale\)/u)
  assert.doesNotMatch(
    spec,
    /page\.route|routeWebSocket|useMockApi|page\.request\.(?:post|put|patch|delete)|localStorage\.setItem|document\.cookie\s*=/u
  )

  assert.match(config, /testDir: "\.\/tests\/e2e-live"/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
  assert.match(
    packageJson,
    /test:e2e:live:contract"\s*:\s*"node --test[^\n]*events-scroll-restoration\.contract\.test\.mjs/u
  )
})
