import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"

import { normalizeNotificationDeadLetterMocks } from "./normalize-generated-msw.mjs"

const handlersPath = new URL("../src/tests/mocks/generated/handlers.ts", import.meta.url)
const packagePath = new URL("../package.json", import.meta.url)

const responseFactory = (source, name) => {
  const start = source.indexOf(`export function ${name}()`)
  assert.notEqual(start, -1, `missing generated response factory ${name}`)
  const next = source.indexOf("\nexport function ", start + 1)
  return source.slice(start, next === -1 ? source.length : next)
}

test("notification dead-letter generated mocks honor literal and numeric constraints", async () => {
  const source = await readFile(handlersPath, "utf8")

  for (const name of [
    "getPurgeNotificationDeadLetters200Response",
    "getRetryNotificationDeadLetters200Response",
  ]) {
    const factory = responseFactory(source, name)
    assert.match(factory, /affected_count: faker\.number\.int\(\{ min: 0 \}\),/u)
    assert.match(factory, /success: true,/u)
    assert.doesNotMatch(factory, /success: faker\.datatype\.boolean\(\),/u)
  }
})

test("the API generation pipeline applies the fail-closed MSW normalizer", async () => {
  const packageJson = JSON.parse(await readFile(packagePath, "utf8"))
  assert.match(packageJson.scripts["generate:api"], /normalize-generated-msw\.mjs/u)
})

test("the MSW normalizer fixes both response factories and rejects generator drift", () => {
  const factory = (name) => `export function ${name}() {
  return {
    affected_count: faker.number.int(),
    success: faker.datatype.boolean(),
  };
}`
  const raw = [
    factory("getPurgeNotificationDeadLetters200Response"),
    factory("getRetryNotificationDeadLetters200Response"),
  ].join("\n")

  const normalized = normalizeNotificationDeadLetterMocks(raw)
  assert.equal(normalized.match(/affected_count: faker\.number\.int\(\{ min: 0 \}\),/gu)?.length, 2)
  assert.equal(normalized.match(/success: true,/gu)?.length, 2)
  assert.throws(
    () => normalizeNotificationDeadLetterMocks(raw.replace("affected_count", "changed_count")),
    /Expected exactly one/u
  )
})
