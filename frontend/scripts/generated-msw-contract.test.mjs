import assert from "node:assert/strict"
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"
import * as prettier from "prettier"
import test from "node:test"
import { setupServer } from "msw/node"

import {
  normalizeGeneratedMswFile,
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

const emittedHandlers = `import { HttpResponse, http } from 'msw'
import { faker } from '@faker-js/faker'

export function getPurgeNotificationDeadLetters200Response() {
  return {
    affected_count: faker.number.int(),
    success: faker.datatype.boolean(),
  }
}

export function getRetryNotificationDeadLetters200Response() {
  return {
    affected_count: faker.number.int(),
    success: faker.datatype.boolean(),
  }
}

export const handlers = [
  http.get('/api/v1/generated', () => {
    const responseJson = { ok: true }
    return HttpResponse.json(responseJson, init);
  }),
]
`

const emittedNative = `import { setupServer } from 'msw/native'
import { handlers } from './handlers'
type NativeServer = Pick<ReturnType<typeof setupServer>, 'listen' | 'close' | 'use' | 'restoreHandlers' | 'resetHandlers' | 'listHandlers' | 'events'>
export const server: NativeServer = setupServer(...handlers)
`

const formatWithRepositoryConfig = async (source, path) => {
  const configPath = fileURLToPath(
    new URL("../src/tests/mocks/generated/handlers.ts", import.meta.url)
  )
  const config = (await prettier.resolveConfig(configPath, { editorconfig: true })) ?? {}
  return prettier.format(source, { ...config, filepath: path })
}

const formatLikeRepository = async (path) => {
  const source = await readFile(path, "utf8")
  await writeFile(path, await formatWithRepositoryConfig(source, path), "utf8")
}

test("generated MSW files stay byte-identical across regeneration and Prettier formatting", async () => {
  const directory = await mkdtemp(join(tmpdir(), "generated-msw-contract-"))
  const handlersPath = join(directory, "handlers.ts")
  const nativePath = join(directory, "native.ts")
  const generateAndFormat = async () => {
    await writeFile(handlersPath, emittedHandlers, "utf8")
    await writeFile(nativePath, emittedNative, "utf8")
    await normalizeGeneratedMswFile(pathToFileURL(handlersPath), pathToFileURL(nativePath))
    for (const path of [nativePath]) {
      const normalized = await readFile(path, "utf8")
      assert.equal(
        normalized,
        await formatWithRepositoryConfig(normalized, path),
        "normalizer output must already match the repository Prettier config"
      )
    }
    await formatLikeRepository(nativePath)
    const firstNormalization = await Promise.all([readFile(handlersPath), readFile(nativePath)])
    await normalizeGeneratedMswFile(pathToFileURL(handlersPath), pathToFileURL(nativePath))
    assert.deepEqual(
      await Promise.all([readFile(handlersPath), readFile(nativePath)]),
      firstNormalization,
      "normalizing existing generated files must be idempotent"
    )
    return firstNormalization
  }

  try {
    const firstGeneration = await generateAndFormat()
    const repeatedGeneration = await generateAndFormat()
    assert.deepEqual(repeatedGeneration, firstGeneration)
    const normalizedNative = firstGeneration[1].toString("utf8")
    assert.match(normalizedNative, /from "msw\/node"/u)
    assert.match(normalizedNative, /type NativeServer = Pick<\n/u)
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})
