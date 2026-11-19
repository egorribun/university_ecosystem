import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { performance } from "node:perf_hooks"
import process from "node:process"
import test from "node:test"
import { clearTimeout, setTimeout } from "node:timers"
import { URL } from "node:url"
import { JSDOM } from "jsdom"
import * as eventsGeometry from "./events-geometry.ts"
import { collectEventsGeometry } from "./events-geometry.ts"

const specUrl = new URL("./events-scroll-restoration.live.spec.ts", import.meta.url)
const geometryUrl = new URL("./events-geometry.ts", import.meta.url)
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
const listUrl = new URL("../../src/features/events/components/EventsList.tsx", import.meta.url)
const cardViewUrl = new URL(
  "../../src/components/events/EventCard/EventCardView.tsx",
  import.meta.url
)

const [
  spec,
  geometry,
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
  eventList,
  eventCardView,
] = await Promise.all([
  readFile(specUrl, "utf8"),
  readFile(geometryUrl, "utf8"),
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
  readFile(listUrl, "utf8"),
  readFile(cardViewUrl, "utf8"),
])

test("live Events history acceptance covers the seeded archive in RU and EN", () => {
  const eventSeedStart = seed.indexOf('"title": "Выпускной вечер 2026"')
  const eventSeedEnd = seed.indexOf("\n]\n", eventSeedStart)
  assert.ok(eventSeedStart >= 0 && eventSeedEnd > eventSeedStart)
  const seededEvent = seed.slice(eventSeedStart, eventSeedEnd)
  assert.match(seededEvent, /"starts_at": _dt\(2026, 6, 28/u)
  assert.match(seededEvent, /"ends_at": _dt\(2026, 6, 28/u)
  assert.match(seed, /"title": "Class of 2026 graduation ceremony"/u)
  assert.match(seed, /ARCHIVE_EVENT_ANCHOR = _dt\(2024, 1, 1, 15, 0\)/u)
  assert.match(seed, /ARCHIVE_EVENT_SOURCES = \(\*EVENTS_DATA\[:8\], EVENTS_DATA\[-1\]\)/u)
  assert.match(seed, /title": f"Архив: \{_archive_source\['title'\]\}"/u)
  assert.match(seed, /title_en": f"Archive: \{_archive_source\['title_en'\]\}"/u)
  assert.match(seed, /async def seed_archived_events/u)
  const archiveSeeder = seed.slice(
    seed.indexOf("async def seed_archived_events"),
    seed.indexOf("async def seed_schedule")
  )
  assert.match(archiveSeeder, /if ends_at >= now:[\s\S]*?raise RuntimeError/u)
  assert.match(archiveSeeder, /Event\.created_by == user\.id/u)
  assert.match(archiveSeeder, /natural_key_collision is not None:[\s\S]*?continue/u)
  assert.match(archiveSeeder, /is_active=True/u)
  assert.match(archiveSeeder, /existing_seed\.is_active = True/u)
  assert.match(seed, /await seed_archived_events\(db, user\)/u)

  const englishEvents = JSON.parse(englishEventsSource)
  const russianEvents = JSON.parse(russianEventsSource)
  assert.equal(englishEvents.pageTitle, "Events")
  assert.equal(englishEvents.tabs.archive, "Past events")
  assert.equal(russianEvents.pageTitle, "Мероприятия")
  assert.equal(russianEvents.tabs.archive, "Прошедшие")
  assert.match(feature, /tab === "archive" \? false/u)
  assert.match(repository, /conditions\.append\(Event\.is_active\.is_\(True\)\)/u)
  assert.match(repository, /if is_active is False:[\s\S]*?Event\.ends_at < now/u)
  assert.match(repository, /order_by\(Event\.starts_at\.asc\(\), Event\.id\.asc\(\)\)/u)
  assert.match(eventList, /xl:grid-cols-4/u)
  assert.match(eventCardView, /h-48 sm:h-52/u)

  assert.match(appearance, /name="language"/u)
  assert.match(appearance, /setLanguage\(value as SupportedLanguage\)/u)
  assert.match(card, /to="\/events\/\$id"[\s\S]*?params=\{\{ id \}\}/u)
  assert.match(detailRoute, /createFileRoute\("\/_auth\/events\/\$id"\)/u)
  assert.match(detailHeader, /<h1[\s\S]*?>\{title\}<\/h1>/u)

  assert.match(spec, /const LANGUAGE_KEY = "ue:language"/u)
  assert.match(spec, /const EVENT_LOCALES = \[/u)
  assert.match(spec, /code: "ru"/u)
  assert.match(spec, /languageOption: \/Русский\|Russian/u)
  assert.match(spec, /eventTitle: \/\^Архив: Открытая лекция: «Будущее ИИ в образовании»\$\/u/u)
  assert.match(spec, /eventTitle: \/\^Archive: Open lecture: The future of AI in education\$\/u/u)
  assert.match(
    spec,
    /expect\.poll\(\(\) => new URL\(page\.url\(\)\)\.pathname\)\.toBe\(["']\/events["']\)/u
  )
  assert.match(spec, /code: "en"/u)
  assert.match(spec, /languageOption: \/Английский\|English/u)
  assert.match(spec, /eventTitle: \/\^Archive: Open lecture: The future of AI in education\$\/u/u)
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
  assert.match(
    spec,
    /await selectedEvent\.click\(\)[\s\S]*?await page\.mouse\.move\(0, 0\)\s+await page\.goBack\(\)/u,
    "the pointer must be moved off the card before the first Back navigation"
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

test("Events geometry reports bounded numeric snapshots without weakening history assertions", () => {
  assert.match(spec, /UE_LIVE_EVENTS_GEOMETRY_V1 project=/u)
  assert.match(spec, /project !== "desktop" && project !== "mobile"/u)
  assert.match(spec, /attempt !== 0 && attempt !== 1/u)
  assert.match(geometry, /cards\s*\.slice\(0, 12\)/u)
  assert.match(geometry, /selected\?\.closest\("#events-tabpanel > \.grid"\)/u)
  assert.match(
    geometry,
    /eventLink\.evaluate\(collectEventsGeometry, undefined, \{ timeout: 500 \}\)/u
  )
  assert.match(spec, /liveTestSlotDeadlineAtMs\(info\)/u)
  assert.match(spec, /liveDeadlineBoundedTimeoutMs\(deadlineAtMs, 500\)/u)
  assert.match(spec, /sampleEventsGeometry\(eventLink, budgetMs\)/u)
  assert.match(spec, /Number\.isSafeInteger\(value\)/u)
  assert.match(spec, /Math\.abs\(value\) > 999_999/u)
  assert.match(geometry, /\{ timeout: 500 \}/u)
  assert.match(spec, /reportEventsGeometry\(selectedEvent, locale\.code, "before"\)/u)
  assert.match(
    spec,
    /finally \{\s*await reportEventsGeometry\(restoredEvent, locale\.code, "back"\)/u
  )
  assert.match(
    spec,
    /finally \{\s*await reportEventsGeometry\(restoredEventAfterForward, locale\.code, "back-forward"\)/u
  )
  assert.equal((spec.match(/\.toBe\(originalPosition\.scrollY\)/gu) ?? []).length, 2)
  assert.equal((spec.match(/\.toBe\(originalPosition\.top\)/gu) ?? []).length, 2)
  const diagnostic = spec.slice(
    spec.indexOf("async function reportEventsGeometry"),
    spec.indexOf("async function openLanguageOptions")
  )
  assert.doesNotMatch(
    diagnostic + geometry,
    /textContent|innerHTML|outerHTML|href|cookie|localStorage/u
  )
})

test("Events geometry measures the populated grid and changes in preceding cards", () => {
  const populatedList = eventList.slice(
    eventList.indexOf("{/* ── Card grid (populated feed) ── */}")
  )
  assert.match(eventList, /<section[\s\S]*?id="events-tabpanel"/u)
  assert.match(populatedList, /<div className="grid [^"]+">\s*\{eventsList\.map/u)
  assert.match(eventCardView, /data-testid="event-card"/u)

  const card = (index) => `
    <div class="css-stagger-item">
      <div class="event-quick-view-host"><article data-testid="event-card">
        <div><h3><a>synthetic event ${index}</a></h3></div>
      </article></div>
    </div>`
  const dom = new JSDOM(`
    <section id="events-tabpanel">
      <div class="grid" id="another-grid">${card("outside")}</div>
      <div class="grid grid-cols-1" id="populated-grid">${card(0)}${card(1)}${card(2)}</div>
    </section>`)
  const { document } = dom.window
  const grid = document.querySelector("#populated-grid")
  const cards = Array.from(grid.querySelectorAll('[data-testid="event-card"]'))
  const selectedLink = cards[2].querySelector("a")
  let firstHeight = 300
  grid.getBoundingClientRect = () => ({ top: -200 })
  cards[0].getBoundingClientRect = () => ({ height: firstHeight })
  cards[1].getBoundingClientRect = () => ({ height: 320 })
  cards[2].getBoundingClientRect = () => ({ height: 340 })
  selectedLink.getBoundingClientRect = () => ({ top: 280 + firstHeight - 300, height: 40 })

  const before = collectEventsGeometry(selectedLink)
  assert.equal(before.gridTop, -200)
  assert.equal(before.selectedIndex, 2)
  assert.equal(before.cardCount, 3)
  assert.deepEqual(before.heights, [300, 320, 340])
  assert.equal(before.linkTop, 280)

  firstHeight = 337
  const after = collectEventsGeometry(selectedLink)
  assert.equal(after.selectedIndex, 2)
  assert.equal(after.cardCount, 3)
  assert.deepEqual(after.heights, [337, 320, 340])
  assert.equal(after.linkTop, 317)

  grid.className = "not-an-events-grid"
  assert.equal(collectEventsGeometry(selectedLink), null)
  dom.window.close()
})

test("Events geometry preserves the card count and height sample limits", () => {
  const dom = new JSDOM('<section id="events-tabpanel"><div class="grid"></div></section>')
  const grid = dom.window.document.querySelector(".grid")
  for (let index = 0; index < 13; index += 1) {
    const wrapper = dom.window.document.createElement("div")
    wrapper.innerHTML = '<article data-testid="event-card"><h3><a>synthetic</a></h3></article>'
    grid.append(wrapper)
  }
  const link = grid.querySelectorAll("a")[12]
  const sample = collectEventsGeometry(link)
  assert.equal(sample.selectedIndex, 12)
  assert.equal(sample.cardCount, 13)
  assert.equal(sample.heights.length, 12)
  for (let index = 13; index < 101; index += 1) {
    grid.append(grid.firstElementChild.cloneNode(true))
  }
  assert.equal(collectEventsGeometry(link), null)
  assert.equal(collectEventsGeometry(dom.window.document.body), null)
  dom.window.close()
})

test("a stalled or late-rejecting geometry read cannot replace the history failure", async () => {
  const originalFailure = new Error("synthetic history assertion")
  const unhandled = []
  const onUnhandled = (error) => unhandled.push(error)
  process.on("unhandledRejection", onUnhandled)
  let rejectEvaluation
  let guard
  let independentTimer
  let independentTimerFired = false
  try {
    const locator = {
      evaluate: (callback, argument, options) => {
        assert.equal(callback, collectEventsGeometry)
        assert.equal(argument, undefined)
        assert.deepEqual(options, { timeout: 500 })
        return new Promise((_resolve, reject) => {
          rejectEvaluation = reject
        })
      },
    }
    independentTimer = setTimeout(() => {
      independentTimerFired = true
    }, 40)
    const acceptance = async () => {
      try {
        throw originalFailure
      } finally {
        await eventsGeometry.sampleEventsGeometry(locator, 20)
      }
    }
    await Promise.race([
      assert.rejects(acceptance(), (error) => error === originalFailure),
      new Promise((_resolve, reject) => {
        guard = setTimeout(() => reject(new Error("geometry observer did not stop waiting")), 1500)
      }),
    ])
    rejectEvaluation(new Error("private late evaluation failure"))
    await new Promise((resolve) => setTimeout(resolve, 60))
    assert.deepEqual(unhandled, [])
    assert.equal(independentTimerFired, true)
  } finally {
    clearTimeout(guard)
    clearTimeout(independentTimer)
    process.off("unhandledRejection", onUnhandled)
  }
})

test("geometry sampling returns fast results and skips an exhausted diagnostic budget", async () => {
  const expected = { selectedIndex: 2 }
  let calls = 0
  const locator = {
    evaluate: async () => {
      calls += 1
      return expected
    },
  }
  assert.equal(await eventsGeometry.sampleEventsGeometry(locator, 0), null)
  assert.equal(await eventsGeometry.sampleEventsGeometry(locator, 501), null)
  assert.equal(calls, 0)
  assert.equal(await eventsGeometry.sampleEventsGeometry(locator, 500), expected)
  assert.equal(calls, 1)
  assert.equal(
    await eventsGeometry.sampleEventsGeometry(
      {
        evaluate: () => {
          throw new Error("private")
        },
      },
      500
    ),
    null
  )
})

test("geometry sampling skips an evaluation whose budget expires before it starts", async (t) => {
  let now = 100
  let calls = 0
  const clock = t.mock.method(performance, "now", () => now)
  try {
    const locator = {
      evaluate: async () => {
        calls += 1
        return null
      },
    }
    const pending = eventsGeometry.sampleEventsGeometry(locator, 20)
    now = 120
    assert.equal(await pending, null)
    assert.equal(calls, 0)
  } finally {
    clock.mock.restore()
  }
})
