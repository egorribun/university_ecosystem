import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import { URL } from "node:url"

const specUrl = new URL("./admin-stories-smoke.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const routeUrl = new URL("../../src/routes/_admin/admin.stories.tsx", import.meta.url)
const pageUrl = new URL("../../src/pages/StoriesAdmin.tsx", import.meta.url)
const storiesApiUrl = new URL("../../src/api/stories.ts", import.meta.url)
const clientUrl = new URL("../../src/api/client.ts", import.meta.url)
const seedUrl = new URL("../../../scripts/seed_demo_data.py", import.meta.url)

function assertAdminStoryListWait(spec) {
  const combined = spec.indexOf("const [response] = await Promise.all([")
  const wait = spec.indexOf("page.waitForResponse(", combined)
  const navigation = spec.indexOf('page.goto("/admin/stories", { waitUntil: "commit" })', wait)
  const end = spec.indexOf("\n  ])", navigation)
  assert.ok(
    combined > 0 && wait > combined && navigation > wait && end > navigation,
    "the list wait must be armed before navigation and awaited together with it"
  )
  const predicate = spec.slice(wait, navigation)
  assert.match(predicate, /requestUrl\.pathname === STORY_LIST_PATH/u)
  assert.match(predicate, /requestUrl\.origin === new URL\(page\.url\(\)\)\.origin/u)
  assert.match(predicate, /response\.request\(\)\.method\(\) === ["']GET["']/u)
  assert.match(predicate, /response\.request\(\)\.frame\(\) === page\.mainFrame\(\)/u)
  const serviceWorkerGuard = predicate.indexOf("response.request().serviceWorker() === null")
  const navigationGuard = predicate.indexOf("!response.request().isNavigationRequest()")
  const frameAccess = predicate.indexOf("response.request().frame()")
  assert.ok(serviceWorkerGuard >= 0 && navigationGuard >= 0 && frameAccess > serviceWorkerGuard)
  assert.ok(frameAccess > navigationGuard)
  assert.match(
    predicate,
    /response\.request\(\)\.headers\(\)\[["']cache-control["']\] === ["']no-cache, no-store["']/u
  )
}

function assertAdminStoryFetch(page) {
  assert.match(
    page,
    /apiClient\.get<StoryItem\[\]>\("\/stories",\s*\{\s*headers:\s*\{\s*"Cache-Control":\s*"no-cache, no-store"\s*\},?\s*\}\)/u
  )
}

test("admin story smoke exercises the real read-only story list and seeded content", async () => {
  const [spec, config, route, page, storiesApi, client, seed] = await Promise.all([
    readFile(specUrl, "utf8"),
    readFile(configUrl, "utf8"),
    readFile(routeUrl, "utf8"),
    readFile(pageUrl, "utf8"),
    readFile(storiesApiUrl, "utf8"),
    readFile(clientUrl, "utf8"),
    readFile(seedUrl, "utf8"),
  ])

  assert.match(spec, /await loginAs\(page, "admin"\)/u)
  assert.match(spec, /page\.goto\("\/admin\/stories", \{ waitUntil: "commit" \}\)/u)
  assert.match(spec, /const STORY_LIST_PATH = ["']\/api\/v1\/stories["']/u)
  assertAdminStoryListWait(spec)
  assert.equal(spec.match(/page\.goto\(/gu)?.length, 1, "the smoke navigates exactly once")
  assert.match(spec, /response\.status\(\)[\s\S]*?\.toBe\(200\)/u)
  assert.match(spec, /Текущие сторис/u)
  assert.match(spec, /🎓 Сессия: советы по подготовке/u)
  assert.match(spec, /stories\.some\(\(story\) => story\.title === SEEDED_STORY_TITLE\)/u)
  assert.match(
    spec,
    /getByRole\("heading",\s*\{\s*level:\s*3,\s*name:\s*SEEDED_STORY_TITLE,\s*exact:\s*true\s*\}\)/u
  )
  assert.match(spec, /storyWrites[\s\S]*?\.toEqual\(\[\]\)/u)
  assert.doesNotMatch(
    spec,
    /page\.request\.(?:post|put|patch|delete)\(|page\.route\(|routeWebSocket\(|\.fulfill\(/u,
    "the smoke must use real server data and must not mutate stories"
  )

  assert.match(route, /createFileRoute\("\/_admin\/admin\/stories"\)/u)
  assertAdminStoryFetch(page)
  const dashboardFetch = storiesApi.match(
    /export function fetchStories\(signal\?: AbortSignal\) \{[\s\S]*?\n\}/u
  )?.[0]
  assert.ok(dashboardFetch, "the dashboard story list request must remain identifiable")
  assert.match(dashboardFetch, /listStoriesApiV1StoriesGet\(options\)/u)
  assert.match(
    dashboardFetch,
    /\.\.\.\(signal \? \{ signal \} : \{\}\)/u,
    "a cancelled dashboard query must abort its story list request"
  )
  assert.doesNotMatch(dashboardFetch, /cache-control|no-cache|no-store/iu)
  assert.doesNotMatch(client, /["']cache-control["']/iu)
  assert.match(page, /if \(!isAdmin\) return/u)
  assert.match(seed, /"title": "🎓 Сессия: советы по подготовке"/u)
  assert.match(config, /testDir:\s*["']\.\/tests\/e2e-live["']/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
})

for (const [name, mutate] of [
  [
    "a late observer",
    (source) =>
      source.replace(
        /( {4}page\.waitForResponse\([\s\S]*?\n {4}\}\),\n)( {4}page\.goto\("\/admin\/stories", \{ waitUntil: "commit" \}\),\n)/u,
        "$2$1"
      ),
  ],
  ["a detached wait", (source) => source.replace("await Promise.all([", "await Promise.race([")],
  [
    "a different path",
    (source) => source.replace("requestUrl.pathname === STORY_LIST_PATH", "true"),
  ],
  [
    "a different origin",
    (source) => source.replace("requestUrl.origin === new URL(page.url()).origin", "true"),
  ],
  [
    "a non-GET request",
    (source) => source.replace('response.request().method() === "GET"', "true"),
  ],
  [
    "a different frame",
    (source) => source.replace("response.request().frame() === page.mainFrame()", "true"),
  ],
  [
    "a service-worker-owned request",
    (source) => source.replace("response.request().serviceWorker() === null", "true"),
  ],
  [
    "a navigation without a frame",
    (source) => source.replace("!response.request().isNavigationRequest()", "true"),
  ],
  [
    "the dashboard request",
    (source) =>
      source.replace(
        'response.request().headers()["cache-control"] === "no-cache, no-store"',
        "true"
      ),
  ],
]) {
  test(`admin story wait contract rejects ${name}`, async () => {
    const source = await readFile(specUrl, "utf8")
    const invalid = mutate(source)
    assert.notEqual(invalid, source)
    assert.throws(() => assertAdminStoryListWait(invalid), assert.AssertionError)
  })
}

for (const [name, mutate] of [
  ["wrong path", (source) => source.replace('"/stories", {', '"/other", {')],
  ["wrong response type", (source) => source.replace("get<StoryItem[]>", "get<unknown>")],
  ["missing no-cache", (source) => source.replace('"no-cache, no-store"', '"no-store"')],
  ["missing no-store", (source) => source.replace('"no-cache, no-store"', '"no-cache"')],
]) {
  test(`admin story source contract rejects ${name}`, async () => {
    const source = await readFile(pageUrl, "utf8")
    const invalid = mutate(source)
    assert.notEqual(invalid, source)
    assert.throws(() => assertAdminStoryFetch(invalid), assert.AssertionError)
  })
}
