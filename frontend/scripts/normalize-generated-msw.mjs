import { readFile, writeFile } from "node:fs/promises"
import { fileURLToPath } from "node:url"

const handlersPath = new URL("../src/tests/mocks/generated/handlers.ts", import.meta.url)
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

export const normalizeGeneratedMswFile = async (path = handlersPath) => {
  const source = await readFile(path, "utf8")
  const normalized = normalizeNotificationDeadLetterMocks(source)
  if (normalized !== source) await writeFile(path, normalized, "utf8")
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  await normalizeGeneratedMswFile()
}
