import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import { URL } from "node:url"

const specUrl = new URL("./news-scroll-restoration.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const seedUrl = new URL("../../../scripts/seed_demo_data.py", import.meta.url)
const fixtureUrl = new URL("./fixtures.ts", import.meta.url)
const listRouteUrl = new URL("../../src/routes/_auth/news.index.tsx", import.meta.url)
const detailRouteUrl = new URL("../../src/routes/_auth/news.$id.tsx", import.meta.url)
const cardUrl = new URL("../../src/components/news/NewsCardContent.tsx", import.meta.url)
const hooksUrl = new URL("../../src/api/hooks/news.ts", import.meta.url)
const appearanceUrl = new URL(
  "../../src/pages/settings/sections/AppearanceSection.tsx",
  import.meta.url
)
const englishSettingsUrl = new URL("../../src/i18n/locales/en/settings.json", import.meta.url)
const russianSettingsUrl = new URL("../../src/i18n/locales/ru/settings.json", import.meta.url)
const repositoryUrl = new URL("../../../app/repositories/news_repository.py", import.meta.url)

const [
  spec,
  config,
  seed,
  fixtures,
  listRoute,
  detailRoute,
  card,
  hooks,
  appearance,
  englishSettingsSource,
  russianSettingsSource,
  repository,
] = await Promise.all([
  readFile(specUrl, "utf8"),
  readFile(configUrl, "utf8"),
  readFile(seedUrl, "utf8"),
  readFile(fixtureUrl, "utf8"),
  readFile(listRouteUrl, "utf8"),
  readFile(detailRouteUrl, "utf8"),
  readFile(cardUrl, "utf8"),
  readFile(hooksUrl, "utf8"),
  readFile(appearanceUrl, "utf8"),
  readFile(englishSettingsUrl, "utf8"),
  readFile(russianSettingsUrl, "utf8"),
  readFile(repositoryUrl, "utf8"),
])

test("live News history acceptance uses a stable read-only demo article", () => {
  const newsStart = seed.indexOf("NEWS_DATA = [")
  const storiesStart = seed.indexOf("STORIES_DATA = [", newsStart)
  assert.ok(newsStart >= 0 && storiesStart > newsStart)
  const seededNews = seed.slice(newsStart, storiesStart)
  assert.equal([...seededNews.matchAll(/^\s+"title":/gmu)].length, 10)
  assert.match(seededNews, /"title": "ГУУ вошёл в топ-20 лучших университетов страны"/u)
  assert.match(seed, /GUU ranks among the country's top 20 universities/u)
  assert.match(seed, /DEMO_PRIMARY_USER_EMAIL = "test@university\.dev"/u)
  assert.match(fixtures, /student:\s*\{\s*email: "test@university\.dev"/u)
  assert.match(seed, /async def seed_news\(db, user: User\)/u)
  assert.match(seed, /News\.author_id == user\.id/u)

  assert.match(listRoute, /createFileRoute\("\/_auth\/news\/"\)/u)
  assert.match(detailRoute, /createFileRoute\("\/_auth\/news\/\$id"\)/u)
  assert.match(card, /to="\/news\/\$id"[\s\S]*?params=\{\{ id \}\}/u)
  assert.match(hooks, /NEWS_PAGE_SIZE = 12/u)
  assert.match(repository, /order_by\(News\.created_at\.desc\(\), News\.id\.desc\(\)\)/u)
  assert.match(appearance, /name="language"/u)
  assert.match(appearance, /setLanguage\(value as SupportedLanguage\)/u)
  const englishSettings = JSON.parse(englishSettingsSource)
  const russianSettings = JSON.parse(russianSettingsSource)
  assert.equal(englishSettings.appearance.language.options.en, "English")
  assert.equal(englishSettings.appearance.language.options.ru, "Russian")
  assert.equal(russianSettings.appearance.language.options.en, "Английский")
  assert.equal(russianSettings.appearance.language.options.ru, "Русский")

  assert.match(config, /testDir: "\.\/tests\/e2e-live"/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
  assert.match(spec, /await loginAs\(page, "student"\)/u)
  assert.match(spec, /switchLanguageThroughSettings\(page, "en"\)/u)
  assert.match(spec, /switchLanguageThroughSettings\(page, "ru"\)/u)
  assert.match(spec, /async function verifyLanguagePersistsAfterReload\(/u)
  const persistenceCheck = spec.slice(
    spec.indexOf("async function verifyLanguagePersistsAfterReload"),
    spec.indexOf("async function verifyNewsHistoryForLanguage")
  )
  assert.match(persistenceCheck, /await page\.reload\(\)/u)
  assert.match(persistenceCheck, /toHaveAttribute\("lang", language\)/u)
  assert.match(persistenceCheck, /localStorage\.getItem\("ue:language"\)/u)
  assert.match(persistenceCheck, /document\.cookie\).*ue:language=\$\{language\}/u)
  assert.match(persistenceCheck, /selectedOption\)\.toBeChecked\(\)/u)
  assert.match(spec, /verifyLanguagePersistsAfterReload\(page, "en"\)/u)
  assert.match(spec, /verifyLanguagePersistsAfterReload\(page, "ru"\)/u)
  assert.ok(
    spec.indexOf('verifyLanguagePersistsAfterReload(page, "en")') <
      spec.indexOf('verifyNewsHistoryForLanguage(page, "en")'),
    "English preference persistence must be checked before the News workflow"
  )
  assert.ok(
    spec.indexOf('verifyLanguagePersistsAfterReload(page, "ru")') <
      spec.indexOf('verifyNewsHistoryForLanguage(page, "ru")'),
    "Russian preference persistence must be checked before the News workflow"
  )
  assert.match(spec, /articleTitle: "ГУУ вошёл в топ-20 лучших университетов страны"/u)
  assert.match(spec, /articleTitle: "GUU ranks among the country's top 20 universities"/u)
  assert.match(spec, /categoryOption: \/Наука\/u/u)
  assert.match(spec, /categoryOption: \/Science\/u/u)
  assert.match(spec, /getByRole\("heading", \{ name: locale\.listHeading, exact: true \}\)/u)
  assert.ok(spec.includes("listHeading: /^(?:University news|University news ?[0-9]+)$/u"))
  assert.ok(
    spec.includes("listHeading: /^(?:Новости университета|Новости университета ?[0-9]+)$/u")
  )
  assert.match(
    spec,
    /expect\.poll\(\(\) => new URL\(page\.url\(\)\)\.pathname\)\.toBe\(["']\/news["']\)/u
  )
  assert.match(spec, /toHaveAttribute\("lang", locale\.language\)/u)
  assert.match(spec, /getByRole\("button", \{ name: locale\.categoryOption \}\)/u)
  assert.match(spec, /searchParams\.get\("cat"\)/u)
  assert.match(spec, /toHaveAttribute\("aria-current", "page"\)/u)
  assert.match(spec, /centerDelta/u)
  assert.match(spec, /beforeFilterScrollY/u)
  assert.match(spec, /await page\.goBack\(\)/u)
  assert.match(spec, /await page\.goForward\(\)/u)
  assert.match(spec, /originalPosition\.scrollY/u)
  assert.match(spec, /originalPosition\.top/u)
  const feedScrollStart = spec.indexOf("const maxScrollY = await page.evaluate")
  const feedScrollEnd = spec.indexOf("const selectedHref =", feedScrollStart)
  const feedScrollSetup = spec.slice(feedScrollStart, feedScrollEnd)
  assert.ok(feedScrollStart >= 0 && feedScrollEnd > feedScrollStart)
  assert.match(feedScrollSetup, /scrollHeight - window\.innerHeight/u)
  assert.match(feedScrollSetup, /maxScrollY[\s\S]*?toBeGreaterThan\(0\)/u)
  assert.match(feedScrollSetup, /const targetScrollY = await selectedNews\.evaluate/u)
  assert.match(feedScrollSetup, /window\.scrollTo\(\{ top: scrollY, behavior: "instant" \}\)/u)
  assert.match(feedScrollSetup, /toBe\(targetScrollY\)/u)
  assert.match(feedScrollSetup, /await expect\(selectedNews\)\.toBeInViewport\(\)/u)
  assert.match(spec, /seeded News article position must be captured after a nonzero feed scroll/u)
  const detailEntryStart = spec.indexOf("await selectedNews.click()")
  const firstBackNavigation = spec.indexOf("await page.goBack()", detailEntryStart)
  const detailEntry = spec.slice(detailEntryStart, firstBackNavigation)
  const firstBackTransition = spec.slice(
    firstBackNavigation,
    spec.indexOf("await page.goForward()")
  )
  assert.match(firstBackTransition, /await expect\(listHeading\)\.toBeVisible\(\)/u)
  assert.match(firstBackTransition, /await expect\(restoredNews\)\.toBeVisible\(\)/u)
  assert.ok(
    detailEntry.includes('window.scrollTo({ top: 320, behavior: "instant" })'),
    "the live scenario creates a non-zero detail-page reading position"
  )
  assert.match(detailEntry, /const detailScrollY = originalDetailPosition\.scrollY/u)
  assert.match(detailEntry, /const detailHeading = page\.getByRole\("heading"/u)
  assert.match(detailEntry, /const originalDetailPosition = await detailHeading\.evaluate/u)
  assert.match(detailEntry, /top:\s*Math\.round\(heading\.getBoundingClientRect\(\)\.top\)/u)
  assert.match(detailEntry, /expect\(\s*detailScrollY,[\s\S]*?\)\.toBeGreaterThan\(\s*0\s*\)/u)
  const forwardNavigation = spec.indexOf("await page.goForward()")
  const finalBackNavigation = spec.indexOf("await page.goBack()", forwardNavigation)
  const forwardTransition = spec.slice(forwardNavigation, finalBackNavigation)
  assert.match(forwardTransition, /await expect\(restoredDetailHeading\)\.toBeVisible\(\)/u)
  assert.ok(
    forwardTransition.includes("originalDetailPosition.scrollY") &&
      forwardTransition.includes("Forward should restore the News article reading position") &&
      forwardTransition.includes("originalDetailPosition.top") &&
      forwardTransition.includes("getBoundingClientRect().top"),
    "Forward must restore both the detail scroll offset and the heading viewport position"
  )
  const afterForwardBack = spec.slice(finalBackNavigation)
  assert.match(afterForwardBack, /await expect\(listHeading\)\.toBeVisible\(\)/u)
  assert.match(afterForwardBack, /await expect\(restoredNewsAfterForward\)\.toBeVisible\(\)/u)
  assert.ok(
    afterForwardBack.includes("originalPosition.top") &&
      afterForwardBack.includes("getBoundingClientRect().top"),
    "Back after Forward must restore the seeded article card to the same viewport position"
  )
  assert.doesNotMatch(
    spec,
    /page\.route|routeWebSocket|useMockApi|page\.request\.(?:post|put|patch|delete)/u
  )
})
