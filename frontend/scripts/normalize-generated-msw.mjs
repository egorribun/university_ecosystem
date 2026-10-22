import { readFile, writeFile } from "node:fs/promises"
import { fileURLToPath } from "node:url"
import * as prettier from "prettier"

const handlersPath = new URL("../src/tests/mocks/generated/handlers.ts", import.meta.url)
const nativePath = new URL("../src/tests/mocks/generated/native.ts", import.meta.url)
const formattingConfigPath = fileURLToPath(handlersPath)
const targetFactories = [
  "getPurgeNotificationDeadLetters200Response",
  "getRetryNotificationDeadLetters200Response",
]

const replaceExactlyOnce = (source, pattern, replacement, label) => {
  const matches = source.match(pattern) ?? []
  if (matches.length !== 1) {
    throw new Error(`Expected exactly one ${label}; found ${matches.length}`)
  }
  return source.replace(pattern, replacement)
}

export const normalizeNotificationDeadLetterMocks = (source) => {
  let normalized = source

  for (const name of targetFactories) {
    const start = normalized.indexOf(`export function ${name}()`)
    if (start === -1) throw new Error(`Missing generated response factory ${name}`)
    const next = normalized.indexOf("\nexport function ", start + 1)
    const end = next === -1 ? normalized.length : next
    const before = normalized.slice(0, start)
    let factory = normalized.slice(start, end)
    const after = normalized.slice(end)

    if (!factory.includes("affected_count: faker.number.int({ min: 0 }),")) {
      factory = replaceExactlyOnce(
        factory,
        /affected_count: faker\.number\.int\(\),/gu,
        "affected_count: faker.number.int({ min: 0 }),",
        `${name} unconstrained affected_count`
      )
    }
    if (!factory.includes("success: true,")) {
      factory = replaceExactlyOnce(
        factory,
        /success: faker\.datatype\.boolean\(\),/gu,
        "success: true,",
        `${name} non-literal success`
      )
    }
    normalized = `${before}${factory}${after}`
  }

  return normalized
}

export const normalizeGeneratedNativeMsw = (source) => {
  const legacyImport = /from (["'])msw\/native\1/gu
  const matches = source.match(legacyImport) ?? []
  if (matches.length === 0 && /from (["'])msw\/node\1/u.test(source)) return source
  if (matches.length !== 1) {
    throw new Error(`Expected exactly one generated msw/native import; found ${matches.length}`)
  }
  return source.replace(legacyImport, 'from "msw/node"')
}

const generatedResponseHelperMarker = "function respondWithGeneratedStatus(body, init) {"
const generatedResponseHelper = `${generatedResponseHelperMarker}
  if (init.status === 204 || init.status === 205 || init.status === 304) {
    return new HttpResponse(null, init);
  }

  return HttpResponse.json(body, init);
}`

export const normalizeGeneratedResponseBodies = (source) => {
  const helperAlreadyPresent = source.includes(generatedResponseHelperMarker)
  const directResponsePattern = /^([ \t]*)return HttpResponse\.json\(responseJson, init\);$/gmu
  const directResponses = source.match(directResponsePattern) ?? []
  const allResponseJsonReturns =
    source.match(/^([ \t]*)return HttpResponse\.json\([^\n;]*, init\);$/gmu) ?? []

  if (helperAlreadyPresent) {
    if (directResponses.length !== 0 || allResponseJsonReturns.length !== 1) {
      throw new Error(
        "Generated MSW response helper drifted from the audited bodyless-status adapter"
      )
    }
    if (!source.includes("return respondWithGeneratedStatus(responseJson, init);")) {
      throw new Error("Generated MSW handlers do not use the audited response helper")
    }
    return source
  }

  if (directResponses.length === 0 || allResponseJsonReturns.length !== directResponses.length) {
    throw new Error("Expected generated handlers to use only HttpResponse.json(responseJson, init)")
  }

  const normalized = source.replace(
    directResponsePattern,
    (_match, indentation) => `${indentation}return respondWithGeneratedStatus(responseJson, init);`
  )
  return replaceExactlyOnce(
    normalized,
    /^import \{ faker \} from ["']@faker-js\/faker["'];?$/gmu,
    (match) => `${match}\n\n${generatedResponseHelper}`,
    "faker import for generated response helper"
  )
}

const formatGeneratedSource = async (source, path) => {
  const config = (await prettier.resolveConfig(formattingConfigPath, { editorconfig: true })) ?? {}
  return prettier.format(source, { ...config, filepath: fileURLToPath(path) })
}

export const normalizeGeneratedMswFile = async (
  path = handlersPath,
  generatedNativePath = nativePath
) => {
  const source = await readFile(path, "utf8")
  const normalized = normalizeGeneratedResponseBodies(normalizeNotificationDeadLetterMocks(source))
  if (normalized !== source) await writeFile(path, normalized, "utf8")

  const nativeSource = await readFile(generatedNativePath, "utf8")
  const normalizedNative = await formatGeneratedSource(
    normalizeGeneratedNativeMsw(nativeSource),
    generatedNativePath
  )
  if (normalizedNative !== nativeSource) {
    await writeFile(generatedNativePath, normalizedNative, "utf8")
  }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  await normalizeGeneratedMswFile()
}
