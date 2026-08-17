import { readFileSync, writeFileSync, mkdirSync } from "node:fs"
import { join, dirname } from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"
import process from "node:process"

const defaultPublicDir = fileURLToPath(new URL("../public", import.meta.url))
const defaultSourcePath = join(defaultPublicDir, "manifest.source.json")

const isPlainObject = (value) =>
  typeof value === "object" && value !== null && !Array.isArray(value)

const deepClone = (value) => JSON.parse(JSON.stringify(value))

const mergeManifests = (base, overrides) => {
  const target = deepClone(base)
  const stack = [{ target, source: overrides }]

  while (stack.length > 0) {
    const { target: currentTarget, source } = stack.pop()
    if (!isPlainObject(source)) continue

    for (const [key, value] of Object.entries(source)) {
      if (Array.isArray(value)) {
        const baseArray = Array.isArray(currentTarget[key]) ? currentTarget[key] : []
        currentTarget[key] = value.map((item, index) => {
          const baseItem = baseArray[index]
          if (isPlainObject(item) && isPlainObject(baseItem)) {
            const merged = deepClone(baseItem)
            stack.push({ target: merged, source: item })
            return merged
          }
          if (isPlainObject(item)) {
            const merged = {}
            stack.push({ target: merged, source: item })
            return merged
          }
          return item
        })
        if (baseArray.length > value.length) {
          currentTarget[key].push(...baseArray.slice(value.length))
        }
      } else if (isPlainObject(value)) {
        const baseObject = isPlainObject(currentTarget[key]) ? currentTarget[key] : {}
        const merged = deepClone(baseObject)
        currentTarget[key] = merged
        stack.push({ target: merged, source: value })
      } else {
        currentTarget[key] = value
      }
    }
  }

  return target
}

const formatManifest = (manifest) => `${JSON.stringify(manifest, null, 2)}\n`

const resolveConfig = (options = {}) => {
  const publicDir = options.publicDir ?? defaultPublicDir
  const sourcePath = options.sourcePath ?? defaultSourcePath
  const check = options.check === true

  const raw = readFileSync(sourcePath, "utf-8")
  const config = JSON.parse(raw)
  if (!config || typeof config !== "object") {
    throw new Error(`Invalid manifest source: ${sourcePath}`)
  }
  const base = config.base
  const locales = config.locales
  const defaultLocale = config.defaultLocale ?? Object.keys(locales ?? {})[0]
  if (!isPlainObject(base) || !isPlainObject(locales)) {
    throw new Error(`Manifest source must define base and locales: ${sourcePath}`)
  }
  if (!defaultLocale || !locales[defaultLocale]) {
    throw new Error(`Default locale "${defaultLocale}" is missing in manifest source`)
  }
  return { publicDir, sourcePath, base, locales, defaultLocale, check }
}

export const generateManifests = (options = {}) => {
  const { publicDir, sourcePath, base, locales, defaultLocale, check } = resolveConfig(options)

  for (const [locale, overrides] of Object.entries(locales)) {
    const manifest = mergeManifests(base, overrides)
    const filename =
      locale === defaultLocale ? "manifest.webmanifest" : `manifest.${locale}.webmanifest`
    const destination = join(publicDir, filename)
    const contents = formatManifest(manifest)

    if (check) {
      let existing
      try {
        existing = readFileSync(destination, "utf-8")
      } catch (error) {
        if (error && error.code === "ENOENT") {
          throw new Error(
            `Generated manifest missing: ${filename}. Run "npm run generate:manifests" to refresh the output.`
          )
        }
        throw error
      }
      if (existing !== contents) {
        throw new Error(
          `Generated manifest stale: ${filename}. Run "npm run generate:manifests" and commit the result.`
        )
      }
    } else {
      mkdirSync(dirname(destination), { recursive: true })
      writeFileSync(destination, contents)
    }
  }

  return { sourcePath, publicDir }
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const check = process.argv.includes("--check")
  try {
    generateManifests({ check })
  } catch (error) {
    console.error(error instanceof Error ? error.message : error)
    process.exit(1)
  }
}
