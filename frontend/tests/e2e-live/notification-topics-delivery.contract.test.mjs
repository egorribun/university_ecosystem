import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL, URLSearchParams } from "node:url"
import { runInNewContext } from "node:vm"
import test from "node:test"
import typescript from "typescript"

const specUrl = new URL("./notification-topics-delivery.live.spec.ts", import.meta.url)

test("notification reads explicitly select the locale of the release marker on every page", async () => {
  const spec = await readFile(specUrl, "utf8")
  const reader = spec.slice(
    spec.indexOf("const listAllNotifications ="),
    spec.indexOf("const waitForOnePersistedNotification =")
  )
  assert.match(reader, /new URLSearchParams\(\{ limit: "100", lang: "ru" \}\)/u)
  assert.match(reader, /if \(cursor\) query\.set\("cursor", cursor\)/u)
  assert.match(reader, /response\.headers\(\)\["content-language"\]/u)
  assert.match(reader, /\.toBe\(\s*"ru"\s*\)/u)
})

test("release delivery retains the Russian body marker and exact recipient assertions", async () => {
  const spec = await readFile(specUrl, "utf8")
  assert.match(
    spec,
    /const releasePayload = \{ version: releaseVersion, notes_ru: releaseNotes \}/u
  )
  assert.match(spec, /expect\(releaseResult\.created\)\.toBe\(1\)/u)
  assert.match(spec, /\(row\.body \?\? ""\)\.includes\(releaseNotes\)/u)
  assert.match(spec, /expect\(repeatedRelease\.created\)\.toBe\(0\)/u)
  assert.match(spec, /expect\(native\.notificationId\)\.toBe\(notificationRow\.id\)/u)
  assert.match(spec, /expect\(native\.entityId\)\.toBe\(expected\.entityId\)/u)
  assert.doesNotMatch(spec, /notes_en: releaseNotes/u)
})

test("native delivery failures report bounded redacted observations before cleanup", async () => {
  const spec = await readFile(specUrl, "utf8")
  const wait = spec.slice(
    spec.indexOf("const waitForNativeNotification ="),
    spec.indexOf("const assertActualDelivery =")
  )
  assert.match(
    wait,
    /catch \(error\) \{\s*await reportLivePushDeliveryObservation\(page, test\.info\(\)\.project\.name, notificationId\)\s*throw error/u
  )
  assert.match(wait, /timeout: 60_000/u)
  assert.match(wait, /\.toBe\(1\)/u)
  assert.doesNotMatch(wait, /probeSubscribe|console\.|JSON\.stringify/u)
})

test("the real notification reader keeps Russian pagination and rejects an English response", async () => {
  const spec = await readFile(specUrl, "utf8")
  const start = spec.indexOf("const listAllNotifications =")
  const end = spec.indexOf("const waitForOnePersistedNotification =")
  assert.ok(start >= 0 && end > start)
  const compiled = typescript.transpileModule(
    `${spec.slice(start, end)}\nglobalThis.readNotifications = listAllNotifications`,
    { compilerOptions: { target: typescript.ScriptTarget.ES2022 } }
  )
  const context = {
    URLSearchParams,
    expect: (value) => ({ toBe: (expected) => assert.equal(value, expected) }),
    expectUuid: (value) => value,
  }
  runInNewContext(compiled.outputText, context)
  const urls = []
  const rows = await context.readNotifications({
    request: {
      get: async (url) => {
        urls.push(url)
        return {
          status: () => 200,
          headers: () => ({ "content-language": "ru" }),
          json: async () =>
            urls.length === 1
              ? { items: [{ id: "first" }], has_more: true, next_cursor: "next" }
              : { items: [{ id: "second" }], has_more: false },
        }
      },
    },
  })
  assert.equal(rows.length, 2)
  assert.equal(urls.length, 2)
  for (const url of urls) {
    assert.equal(new URL(url, "https://example.test").searchParams.get("lang"), "ru")
  }
  assert.equal(new URL(urls[1], "https://example.test").searchParams.get("cursor"), "next")
  await assert.rejects(
    context.readNotifications({
      request: {
        get: async () => ({
          status: () => 200,
          headers: () => ({ "content-language": "en" }),
        }),
      },
    }),
    { code: "ERR_ASSERTION" }
  )
})
