import { describe, expect, it } from "vitest"
import { readdirSync, readFileSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { supportedLngs } from "@/i18n/metadata"

const __dirname = path.dirname(fileURLToPath(import.meta.url))

const LOCALES_ROOT = path.resolve(__dirname, "../i18n/locales")
const BASE_LOCALE = path.join(LOCALES_ROOT, "en")

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

describe("i18n locales parity against base en", () => {
  const baseFiles = collectLocaleFiles(BASE_LOCALE)
  const baseFileNames = Array.from(baseFiles.keys()).sort()

  const targets = supportedLngs.filter((lng) => lng !== "en")

  for (const lng of targets) {
    const localePath = path.join(LOCALES_ROOT, lng)
    const localeFiles = collectLocaleFiles(localePath)
    const localeFileNames = Array.from(localeFiles.keys()).sort()

    it(`${lng} exposes the same set of locale files as en`, () => {
      expect(localeFileNames).toEqual(baseFileNames)
    })

    const allFiles = new Set([...baseFiles.keys(), ...localeFiles.keys()])

    for (const relativePath of allFiles) {
      it(`${lng} has matching keys in ${relativePath}`, () => {
        expect(localeFiles.has(relativePath)).toBe(true)
        expect(baseFiles.has(relativePath)).toBe(true)

        const baseJson = readJson(baseFiles.get(relativePath)!)
        const targetJson = readJson(localeFiles.get(relativePath)!)

        const baseKeys = Array.from(flattenKeys(baseJson)).sort()
        const targetKeys = Array.from(flattenKeys(targetJson)).sort()

        const missingInTarget = baseKeys.filter((key) => !targetKeys.includes(key))
        const missingInBase = targetKeys.filter((key) => !baseKeys.includes(key))

        const errorMessages = [] as string[]
        if (missingInTarget.length > 0) {
          errorMessages.push(
            `Missing ${missingInTarget.length} key(s) in ${lng} → ${missingInTarget.join(", ")}`
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
  }
})




