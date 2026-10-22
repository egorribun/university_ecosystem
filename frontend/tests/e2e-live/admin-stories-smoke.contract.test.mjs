import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import { URL } from "node:url"

const specUrl = new URL("./admin-stories-smoke.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const routeUrl = new URL("../../src/routes/_admin/admin.stories.tsx", import.meta.url)
const pageUrl = new URL("../../src/pages/StoriesAdmin.tsx", import.meta.url)
const seedUrl = new URL("../../../scripts/seed_demo_data.py", import.meta.url)

test("admin story smoke exercises the real read-only story list and seeded content", async () => {
  const [spec, config, route, page, seed] = await Promise.all([
    readFile(specUrl, "utf8"),
    readFile(configUrl, "utf8"),
    readFile(routeUrl, "utf8"),
    readFile(pageUrl, "utf8"),
    readFile(seedUrl, "utf8"),
  ])

  assert.match(spec, /await loginAs\(page, "admin"\)/u)
  assert.match(spec, /page\.goto\("\/admin\/stories"\)/u)
  assert.match(spec, /const STORY_LIST_PATH = ["']\/api\/v1\/stories["']/u)
  assert.match(
    spec,
    /waitForResponse\([\s\S]*?requestUrl\.pathname === STORY_LIST_PATH[\s\S]*?method\(\) === ["']GET["']/u
  )
  assert.match(spec, /response\.status\(\)[\s\S]*?\.toBe\(200\)/u)
  assert.match(spec, /Текущие сторис/u)
  assert.match(spec, /🎓 Сессия: советы по подготовке/u)
  assert.match(spec, /storyWrites[\s\S]*?\.toEqual\(\[\]\)/u)
  assert.doesNotMatch(
    spec,
    /page\.request\.(?:post|put|patch|delete)\(|page\.route\(|routeWebSocket\(|\.fulfill\(/u,
    "the smoke must use real server data and must not mutate stories"
  )

  assert.match(route, /createFileRoute\("\/_admin\/admin\/stories"\)/u)
  assert.match(page, /apiClient\.get<StoryItem\[\]>\("\/stories"\)/u)
  assert.match(page, /if \(!isAdmin\) return/u)
  assert.match(seed, /"title": "🎓 Сессия: советы по подготовке"/u)
  assert.match(config, /testDir:\s*["']\.\/tests\/e2e-live["']/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
})
