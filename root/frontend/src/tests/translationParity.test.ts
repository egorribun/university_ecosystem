import { describe, expect, it } from "vitest"
import { readdirSync, readFileSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = path.dirname(fileURLToPath(import.meta.url))

const LOCALES_ROOT = path.resolve(__dirname, "../i18n/locales")
const BASE_LOCALE = path.join(LOCALES_ROOT, "en")
const TARGET_LOCALE = path.join(LOCALES_ROOT, "ru")

/**
 * Перечень путей, которые можно пропускать при сравнении.
 * Указывайте полный путь через точку (например, "events.synonyms").
 */
const IGNORED_PATH_PREFIXES: string[] = [
  // 'events.synonyms',
]

const isIgnored = (keyPath: string) =>
  IGNORED_PATH_PREFIXES.some(
    (ignoredPrefix) => keyPath === ignoredPrefix || keyPath.startsWith(`${ignoredPrefix}.`)
  )

type JsonValue = string | number | boolean | null | JsonObject | JsonValue[]

interface JsonObject {
  [key: string]: JsonValue
}

const readJson = (filePath: string) => JSON.parse(readFileSync(filePath, "utf-8")) as JsonObject

const flattenKeys = (value: JsonValue, prefix = "", keys: Set<string> = new Set<string>()) => {
  if (Array.isArray(value)) {
    if (prefix && !isIgnored(prefix)) {
      keys.add(prefix)
    }
    return keys
  }

  if (value && typeof value === "object") {
    for (const [key, nestedValue] of Object.entries(value)) {
      const nextPath = prefix ? `${prefix}.${key}` : key
      if (isIgnored(nextPath)) {
        continue
      }

      if (nestedValue && typeof nestedValue === "object" && !Array.isArray(nestedValue)) {
        flattenKeys(nestedValue, nextPath, keys)
        continue
      }

      keys.add(nextPath)
    }

    return keys
  }

  if (prefix) {
    keys.add(prefix)
  }

  return keys
}

const collectLocaleFiles = (localePath: string) => {
  const files = new Map<string, string>()

  const walk = (relativeDir: string) => {
    const absoluteDir = path.join(localePath, relativeDir)
    for (const entry of readdirSync(absoluteDir, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        walk(path.join(relativeDir, entry.name))
        continue
      }

      if (!entry.isFile()) {
        continue
      }

      if (!entry.name.endsWith(".json")) {
        continue
      }

      const relativePath = path.join(relativeDir, entry.name).split(path.sep).join(path.posix.sep)
      files.set(relativePath, path.join(absoluteDir, entry.name))
    }
  }

  walk("")

  return files
}

describe("i18n locales parity between en and ru", () => {
  const baseFiles = collectLocaleFiles(BASE_LOCALE)
  const targetFiles = collectLocaleFiles(TARGET_LOCALE)

  const baseFileNames = Array.from(baseFiles.keys()).sort()
  const targetFileNames = Array.from(targetFiles.keys()).sort()

  it("exposes the same set of locale files", () => {
    expect(targetFileNames).toEqual(baseFileNames)
  })

  const allFiles = new Set([...baseFiles.keys(), ...targetFiles.keys()])

  for (const relativePath of allFiles) {
    it(`has matching keys in ${relativePath}`, () => {
      expect(targetFiles.has(relativePath)).toBe(true)
      expect(baseFiles.has(relativePath)).toBe(true)

      const baseJson = readJson(baseFiles.get(relativePath)!)
      const targetJson = readJson(targetFiles.get(relativePath)!)

      const baseKeys = Array.from(flattenKeys(baseJson)).sort()
      const targetKeys = Array.from(flattenKeys(targetJson)).sort()

      const missingInTarget = baseKeys.filter((key) => !targetKeys.includes(key))
      const missingInBase = targetKeys.filter((key) => !baseKeys.includes(key))

      const errorMessages = [] as string[]
      if (missingInTarget.length > 0) {
        errorMessages.push(
          `Missing ${missingInTarget.length} key(s) in ru → ${missingInTarget.join(", ")}`
        )
      }

      if (missingInBase.length > 0) {
        errorMessages.push(
          `Missing ${missingInBase.length} key(s) in en → ${missingInBase.join(", ")}`
        )
      }

      if (errorMessages.length > 0) {
        throw new Error(errorMessages.join("\n"))
      }

      expect(targetKeys).toEqual(baseKeys)
    })
  }
})
