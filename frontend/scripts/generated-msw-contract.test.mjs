import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import { setupServer } from "msw/node"

import {
  normalizeGeneratedNativeMsw,
  normalizeGeneratedResponseBodies,
  normalizeNotificationDeadLetterMocks,
} from "./normalize-generated-msw.mjs"
import { handlers } from "../src/tests/mocks/generated/handlers.ts"

globalThis.location ??= new URL("http://localhost/")
const server = setupServer(...handlers)
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

test("generated bodyless and JSON status semantics survive actual HTTP handlers", async () => {
  const generatedSource = await readFile(handlersPath, "utf8")
  assert.match(generatedSource, /return respondWithGeneratedStatus\(responseJson, init\);/u)
  assert.doesNotMatch(generatedSource, /return HttpResponse\.json\(responseJson, init\);/u)
  assert.match(generatedSource, /function respondWithGeneratedStatus\(body, init\)/u)
  assert.match(
    generatedSource,
    /init\.status === 204 \|\| init\.status === 205 \|\| init\.status === 304/u
  )
  assert.match(generatedSource, /return new HttpResponse\(null, init\)/u)
  assert.match(generatedSource, /return HttpResponse\.json\(body, init\)/u)

  const unnormalized = [
    'import { HttpResponse, http } from "msw";',
    'import { faker } from "@faker-js/faker";',
    "return HttpResponse.json(responseJson, init);",
  ].join("\n")
  const normalized = normalizeGeneratedResponseBodies(unnormalized)
  assert.equal(
    normalized.match(/return respondWithGeneratedStatus\(responseJson, init\);/gu)?.length,
    1
  )
  assert.equal(normalizeGeneratedResponseBodies(normalized), normalized)
  assert.throws(
    () => normalizeGeneratedResponseBodies("export const handlers = []"),
    /Expected generated handlers/u
  )

  server.listen({ onUnhandledFrame: "error" })
  try {
    const bodyless = await fetch("http://localhost/api/v1/csp-report", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: "{}",
    })
    assert.equal(bodyless.status, 204)
    assert.equal(await bodyless.text(), "")
    assert.equal(bodyless.headers.has("content-type"), false)

    const json = await fetch("http://localhost/api/v1/auth/mfa/email/verification/start", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: "{}",
    })
    assert.equal(json.status, 200)
    assert.equal(json.headers.get("content-type"), "application/json")
    const jsonBody = await json.json()
    assert.equal(typeof jsonBody, "object")
    assert.notEqual(jsonBody, null)
  } finally {
    server.close()
  }
})

test("generated native mocks target the MSW Node entry point after v3 migration", async () => {
  const source = await readFile(
    new URL("../src/tests/mocks/generated/native.ts", import.meta.url),
    "utf8"
  )
  assert.match(source, /from ["']msw\/node["']/u)
  assert.equal(
    normalizeGeneratedNativeMsw("import { setupServer } from 'msw/native'"),
    'import { setupServer } from "msw/node"'
  )
  assert.equal(
    normalizeGeneratedNativeMsw('import { setupServer } from "msw/node"'),
    'import { setupServer } from "msw/node"'
  )
  assert.throws(
    () => normalizeGeneratedNativeMsw("import { setupServer } from 'msw/browser'"),
    /Expected exactly one/u
  )
})
