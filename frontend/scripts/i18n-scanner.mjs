#!/usr/bin/env node

/**
 * AST-aware i18n contract scanner.
 *
 * The scanner intentionally lives outside the application bundle.  It is used
 * by CI and by the local `i18n:check` command, so it can inspect TypeScript and
 * TSX without adding runtime dependencies to the product.  Translation keys
 * are resolved against the checked-in locale catalogues and dynamic keys must
 * be represented by an explicit, finite registry entry.
 */

import { readFile, readdir } from "node:fs/promises"
import { existsSync, readFileSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { parse as babelParse } from "@babel/parser"

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url))
const FRONTEND_ROOT = path.resolve(SCRIPT_DIR, "..")
const DEFAULT_SOURCE_ROOT = path.join(FRONTEND_ROOT, "src")
const DEFAULT_LOCALE_ROOT = path.join(FRONTEND_ROOT, "src", "i18n", "locales")
const DEFAULT_REGISTRY_FILE = path.join(FRONTEND_ROOT, "src", "i18n", "registry.ts")

const SOURCE_EXTENSIONS = new Set([".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"])
const SKIPPED_DIRECTORIES = new Set([
  ".git",
  ".next",
  "coverage",
  "dist",
  "generated",
  "node_modules",
  "test",
  "tests",
  "__tests__",
  "vendor",
  ".storybook",
])
const SKIPPED_FILE_PATTERNS = [/(?:^|[._-])(test|spec|stories?)(?:[._-]|$)/iu, /^setupTests\./iu]
const USER_FACING_ATTRIBUTES = new Set([
  "alt",
  "aria-label",
  "aria-description",
  "aria-valuetext",
  "label",
  "placeholder",
  "title",
  "description",
])
const NON_USER_FACING_TAGS = new Set(["script", "style", "code", "pre"])
const PLURAL_SUFFIX = /_(zero|one|two|few|many|other)$/u
const PLACEHOLDER = /\{\{\s*-?\s*([\w.-]+)(?:\s*,\s*([^}]+?))?\s*\}\}/gu

/** @typedef {{ code: string, message: string, filePath?: string, line?: number, column?: number, key?: string }} I18nError */

function error(code, message, nodeOrFile, key) {
  const location = nodeOrFile && typeof nodeOrFile === "object" ? nodeOrFile.loc?.start : undefined
  const filePath = typeof nodeOrFile === "string" ? nodeOrFile : undefined
  return {
    code,
    message,
    ...(filePath ? { filePath } : {}),
    ...(location?.line ? { line: location.line } : {}),
    ...(location?.column !== undefined ? { column: location.column + 1 } : {}),
    ...(key ? { key } : {}),
  }
}

function unique(values) {
  return [...new Set(values)]
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value)
}

function flattenLocale(value, prefix = "", output = new Map(), nodes = new Set()) {
  if (prefix) nodes.add(prefix)
  if (Array.isArray(value)) {
    output.set(prefix, value)
    return { values: output, nodes }
  }
  if (isObject(value)) {
    for (const [key, child] of Object.entries(value)) {
      const next = prefix ? `${prefix}.${key}` : key
      flattenLocale(child, next, output, nodes)
    }
  } else if (prefix) {
    output.set(prefix, value)
  }
  return { values: output, nodes }
}

function catalogueInfo(catalogues = {}) {
  const result = {}
  for (const [locale, catalogue] of Object.entries(catalogues)) {
    const namespaces = {}
    for (const [namespace, resource] of Object.entries(catalogue ?? {})) {
      const flattened = flattenLocale(resource)
      namespaces[namespace] = flattened
    }
    result[locale] = namespaces
  }
  return result
}

function allNamespaceKeys(info, locale) {
  const keys = new Set()
  for (const [namespace, resource] of Object.entries(info[locale] ?? {})) {
    for (const key of resource.values.keys()) keys.add(`${namespace}:${key}`)
    for (const key of resource.nodes) keys.add(`${namespace}:${key}`)
  }
  return keys
}

function splitTranslationKey(rawKey, defaultNamespace = "common") {
  const value = String(rawKey).trim()
  const separator = value.indexOf(":")
  if (separator === -1)
    return { namespace: defaultNamespace, path: value, key: `${defaultNamespace}:${value}` }
  return {
    namespace: value.slice(0, separator) || defaultNamespace,
    path: value.slice(separator + 1),
    key: value,
  }
}

function keyExists(info, locale, rawKey, defaultNamespace = "common") {
  const { namespace, path: resourcePath } = splitTranslationKey(rawKey, defaultNamespace)
  const resource = info[locale]?.[namespace]
  if (!resource) return false
  if (resource.values.has(resourcePath) || resource.nodes.has(resourcePath)) return true
  const base = resourcePath.replace(PLURAL_SUFFIX, "")
  for (const candidate of resource.values.keys()) {
    if (candidate.replace(PLURAL_SUFFIX, "") === base) return true
  }
  return false
}

function placeholderNames(value) {
  const names = []
  const text = typeof value === "string" ? value : ""
  for (const match of text.matchAll(PLACEHOLDER)) names.push(match[1])
  return unique(names).sort()
}

function placeholderSpecs(value) {
  const specs = new Map()
  const text = typeof value === "string" ? value : ""
  for (const match of text.matchAll(PLACEHOLDER)) {
    specs.set(match[1], match[2]?.trim().toLowerCase() ?? "")
  }
  return [...specs.entries()].sort(([left], [right]) => left.localeCompare(right))
}

function parseAst(source, filePath = "source.tsx") {
  const plugins = [
    "typescript",
    "jsx",
    "classProperties",
    "classPrivateProperties",
    "classPrivateMethods",
    "decorators-legacy",
    "dynamicImport",
    "importMeta",
    "topLevelAwait",
    "optionalChaining",
    "nullishCoalescingOperator",
  ]
  try {
    return babelParse(source, {
      sourceType: "unambiguous",
      plugins,
      errorRecovery: false,
      ranges: false,
      attachComment: false,
      sourceFilename: filePath,
    })
  } catch {
    const suffix =
      path.extname(filePath).toLowerCase() === ".tsx" ? ["typescript", "jsx"] : ["typescript"]
    return babelParse(source, {
      sourceType: "unambiguous",
      plugins: suffix,
      errorRecovery: false,
      sourceFilename: filePath,
    })
  }
}

function walkAst(node, visit, parent = null, ancestors = []) {
  if (!node || typeof node !== "object") return
  visit(node, parent, ancestors)
  for (const [property, value] of Object.entries(node)) {
    if (property === "loc" || property === "start" || property === "end" || property === "tokens")
      continue
    if (Array.isArray(value)) {
      for (const child of value) {
        if (child && typeof child === "object" && typeof child.type === "string") {
          walkAst(child, visit, node, [...ancestors, node])
        }
      }
    } else if (value && typeof value === "object" && typeof value.type === "string") {
      walkAst(value, visit, node, [...ancestors, node])
    }
  }
}

function nodeString(node) {
  if (!node) return undefined
  if (node.type === "StringLiteral" || node.type === "DirectiveLiteral") return node.value
  if (node.type === "TemplateLiteral" && node.expressions.length === 0)
    return node.quasis[0]?.value?.cooked ?? ""
  return undefined
}

function memberPropertyName(node) {
  if (!node) return undefined
  if (!node.computed && node.property?.type === "Identifier") return node.property.name
  return node.computed ? nodeString(node.property) : undefined
}

function isTranslationCallee(node) {
  if (!node) return false
  if (node.type === "Identifier") return node.name === "t" || node.name === "translate"
  if (node.type === "MemberExpression" || node.type === "OptionalMemberExpression") {
    return memberPropertyName(node) === "t"
  }
  return false
}

function isUseTranslationCallee(node) {
  if (!node) return false
  if (node.type === "Identifier") return node.name === "useTranslation"
  if (node.type === "MemberExpression" || node.type === "OptionalMemberExpression") {
    return memberPropertyName(node) === "useTranslation"
  }
  return false
}

function expressionPattern(node, source) {
  if (!node) return undefined
  const literal = nodeString(node)
  if (literal !== undefined) return { kind: "static", key: literal }
  if (node.type === "TemplateLiteral") {
    let pattern = ""
    for (let index = 0; index < node.quasis.length; index += 1) {
      pattern += node.quasis[index]?.value?.cooked ?? ""
      if (index < node.expressions.length) {
        const expression = node.expressions[index]
        const expressionText = source.slice(expression.start, expression.end).trim()
        pattern += `\${${expressionText}}`
      }
    }
    return { kind: node.expressions.length ? "dynamic" : "static", key: pattern }
  }
  return {
    kind: "dynamic",
    key: source.slice(node.start ?? 0, node.end ?? 0).trim() || "<dynamic>",
  }
}

function namespaceFromHook(ast) {
  let namespace = "common"
  walkAst(ast, (node) => {
    if (node.type !== "CallExpression" || !isUseTranslationCallee(node.callee)) return
    const first = node.arguments?.[0]
    const value = nodeString(first)
    if (value) namespace = value
    else if (first?.type === "ArrayExpression") {
      const firstNamespace = nodeString(first.elements?.[0])
      if (firstNamespace) namespace = firstNamespace
    }
  })
  return namespace
}

function attributeName(node) {
  if (!node?.name) return undefined
  if (node.name.type === "JSXIdentifier") return node.name.name
  if (node.name.type === "JSXNamespacedName")
    return `${node.name.namespace.name}:${node.name.name.name}`
  return undefined
}

function isBootLoaderFile(filePath) {
  return /(?:^|[\\/])BrandBootLoader\.[cm]?[jt]sx?$/u.test(filePath)
}

function scanRawLiterals(ast, filePath, errors) {
  if (isBootLoaderFile(filePath)) return
  walkAst(ast, (node, parent, ancestors) => {
    if (node.type === "JSXText") {
      const value = node.value.replace(/\s+/gu, " ").trim()
      const parentName = parent?.openingElement?.name?.name
      if (
        value &&
        /\p{L}/u.test(value) &&
        !NON_USER_FACING_TAGS.has(parentName) &&
        !isTechnicalLiteral(value, filePath)
      ) {
        errors.push(
          error(
            "RAW_USER_FACING_LITERAL",
            `Raw user-facing JSX text must use a translation key: ${JSON.stringify(value)}`,
            node
          )
        )
      }
      return
    }
    if (node.type === "JSXAttribute") {
      const name = attributeName(node)
      const value = nodeString(node.value)
      if (
        name &&
        USER_FACING_ATTRIBUTES.has(name) &&
        value &&
        /\p{L}/u.test(value) &&
        !isTechnicalLiteral(value, filePath)
      ) {
        errors.push(
          error(
            "RAW_USER_FACING_LITERAL",
            `Raw user-facing attribute ${name} must use a translation key`,
            node,
            value
          )
        )
      }
      return
    }
    if (node.type === "StringLiteral" && parent?.type === "JSXExpressionContainer") {
      const element = ancestors.findLast((ancestor) => ancestor.type === "JSXElement")
      const name = element?.openingElement?.name?.name
      if (
        element &&
        !NON_USER_FACING_TAGS.has(name) &&
        /\p{L}/u.test(node.value) &&
        !isTechnicalLiteral(node.value, filePath)
      ) {
        errors.push(
          error(
            "RAW_USER_FACING_LITERAL",
            "Raw user-facing JSX expression must use a translation key",
            node,
            node.value
          )
        )
      }
    }
  })
}

function isTechnicalLiteral(value, filePath = "") {
  const normalized = value.trim()
  if (!normalized) return true
  if (normalized === "© OpenStreetMap") return true
  if (["KB", "Esc", "+K", "of", "Page", "row(s) selected."].includes(normalized)) return true
  if (/^(?:XXXX-){3}XXXX$/u.test(normalized)) return true
  if (/^[A-Z0-9]{3,}(?:-[A-Z0-9]{2,})+$/u.test(normalized)) return true
  if (/^[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}$/u.test(normalized)) return true
  if (normalized === "LHCI RENDER START") return true
  if (
    (normalized === "Error details" || normalized === "Trace ID:") &&
    /ErrorBoundary/u.test(filePath)
  )
    return true
  return false
}

function registryLookup(pattern, dynamicRegistry) {
  if (!dynamicRegistry || typeof dynamicRegistry !== "object") return undefined
  const canonical = pattern.replace(/\s+/gu, " ").trim()
  if (Array.isArray(dynamicRegistry[pattern])) return dynamicRegistry[pattern]
  if (Array.isArray(dynamicRegistry[canonical])) return dynamicRegistry[canonical]
  const normalized = canonical.replace(/\$\{[^}]+\}/gu, "${}")
  for (const [candidate, values] of Object.entries(dynamicRegistry)) {
    if (!Array.isArray(values) || candidate.includes("*")) continue
    if (
      candidate
        .replace(/\s+/gu, " ")
        .trim()
        .replace(/\$\{[^}]+\}/gu, "${}") === normalized
    )
      return values
  }
  return undefined
}

function callHasObjectProperty(call, propertyName) {
  const options = call.arguments?.[1]
  if (!options || options.type !== "ObjectExpression") return false
  return options.properties.some((property) => {
    if (property.type === "SpreadElement") return true
    const key = property.key
    return key?.type === "Identifier" ? key.name === propertyName : nodeString(key) === propertyName
  })
}

function hasPluralVariants(info, locale, rawKey, defaultNamespace) {
  const { namespace, path: resourcePath } = splitTranslationKey(rawKey, defaultNamespace)
  const resource = info[locale]?.[namespace]
  if (!resource || resource.values.has(resourcePath)) return false
  return [...resource.values.keys()].some(
    (candidate) => candidate.replace(PLURAL_SUFFIX, "") === resourcePath
  )
}

function scanFormatterConstructors(ast, source, filePath, errors) {
  walkAst(ast, (node) => {
    if (node.type !== "NewExpression") return
    const callee = node.callee
    if (callee?.type !== "MemberExpression" || callee.object?.name !== "Intl") return
    const formatter = memberPropertyName(callee)
    if (!new Set(["DateTimeFormat", "NumberFormat", "RelativeTimeFormat"]).has(formatter)) return
    if (node.arguments?.length) return
    const trailingSource = source.slice(node.end ?? 0, (node.end ?? 0) + 100)
    // A locale-less DateTimeFormat is valid when it is used solely to obtain
    // the host time zone; all user-visible formatting must pass a locale.
    if (formatter === "DateTimeFormat" && /\.resolvedOptions\(\)\.timeZone/u.test(trailingSource))
      return
    errors.push(
      error("FORMATTER_LOCALE_MISSING", `${formatter} must receive an explicit locale`, node)
    )
  })
}

function scanSource(source, options = {}) {
  const filePath = options.filePath ?? "source.tsx"
  const catalogs = options.catalogs ?? {}
  const info = options.catalogInfo ?? catalogueInfo(catalogs)
  const dynamicRegistry = options.dynamicRegistry ?? {}
  const errors = []
  const references = []
  let ast
  try {
    ast = parseAst(source, filePath)
  } catch (parseError) {
    errors.push(
      error("PARSE_ERROR", `Unable to parse ${filePath}: ${parseError.message}`, filePath)
    )
    return { errors, references, dynamicReferences: [], rawLiterals: [] }
  }
  const defaultNamespace = options.defaultNamespace ?? namespaceFromHook(ast)
  const dynamicReferences = []

  walkAst(ast, (node) => {
    if (node.type !== "CallExpression" || !isTranslationCallee(node.callee)) return
    const firstArgument = node.arguments?.[0]
    const pattern = expressionPattern(firstArgument, source)
    if (!pattern) return
    if (pattern.kind === "dynamic") {
      const registered = registryLookup(pattern.key, dynamicRegistry)
      const dynamicReference = {
        pattern: pattern.key,
        filePath,
        line: node.loc?.start?.line,
        column: node.loc?.start?.column !== undefined ? node.loc.start.column + 1 : undefined,
        registered: Boolean(registered),
      }
      dynamicReferences.push(dynamicReference)
      if (!registered) {
        errors.push(
          error(
            "DYNAMIC_KEY_UNREGISTERED",
            `Dynamic translation key ${pattern.key} must have a finite registry entry`,
            node,
            pattern.key
          )
        )
        return
      }
      if (registered.length === 0) {
        errors.push(
          error(
            "DYNAMIC_KEY_EMPTY_REGISTRY",
            `Dynamic translation key ${pattern.key} has an empty registry entry`,
            node,
            pattern.key
          )
        )
        return
      }
      for (const concreteKey of registered) {
        if (typeof concreteKey !== "string" || concreteKey.includes("*")) {
          errors.push(
            error(
              "DYNAMIC_KEY_WILDCARD",
              `Dynamic translation registry entry ${String(concreteKey)} must be a concrete key`,
              node,
              pattern.key
            )
          )
          continue
        }
        for (const locale of Object.keys(info)) {
          if (!keyExists(info, locale, concreteKey, defaultNamespace)) {
            errors.push(
              error(
                "DYNAMIC_KEY_MISSING",
                `Dynamic registry key ${concreteKey} is missing from ${locale}`,
                node,
                concreteKey
              )
            )
          }
        }
        references.push({ key: concreteKey, dynamic: true, filePath, line: node.loc?.start?.line })
      }
      return
    }

    const { namespace, path: resourcePath } = splitTranslationKey(pattern.key, defaultNamespace)
    const canonicalKey = `${namespace}:${resourcePath}`
    references.push({ key: canonicalKey, dynamic: false, filePath, line: node.loc?.start?.line })
    for (const locale of Object.keys(info)) {
      if (!keyExists(info, locale, pattern.key, defaultNamespace)) {
        errors.push(
          error(
            "TRANSLATION_KEY_MISSING",
            `Translation key ${canonicalKey} is missing from ${locale}`,
            node,
            canonicalKey
          )
        )
      }
    }
    if (
      Object.keys(info).some((locale) =>
        hasPluralVariants(info, locale, pattern.key, defaultNamespace)
      ) &&
      !callHasObjectProperty(node, "count")
    ) {
      errors.push(
        error(
          "PLURAL_COUNT_MISSING",
          `Plural translation ${canonicalKey} must receive a count option`,
          node,
          canonicalKey
        )
      )
    }
  })

  scanRawLiterals(ast, filePath, errors)
  scanFormatterConstructors(ast, source, filePath, errors)
  const locatedErrors = errors.map((entry) => (entry.filePath ? entry : { ...entry, filePath }))
  return {
    errors: locatedErrors,
    references,
    dynamicReferences,
    rawLiterals: locatedErrors.filter((entry) => entry.code === "RAW_USER_FACING_LITERAL"),
  }
}

function scanLocaleCatalogs(catalogues = {}) {
  const info = catalogueInfo(catalogues)
  const errors = []
  const locales = Object.keys(info)
  if (locales.length < 2) {
    errors.push(
      error(
        "LOCALE_COUNT",
        "At least two locale catalogues are required (for example en and ru)",
        "locales"
      )
    )
    return { errors, locales, info }
  }
  const referenceLocale = locales[0]
  const referenceKeys = new Set()
  for (const [namespace, resource] of Object.entries(info[referenceLocale] ?? {})) {
    for (const key of resource.values.keys()) referenceKeys.add(`${namespace}:${key}`)
  }
  for (const locale of locales.slice(1)) {
    const localeKeys = new Set()
    for (const [namespace, resource] of Object.entries(info[locale] ?? {})) {
      for (const key of resource.values.keys()) localeKeys.add(`${namespace}:${key}`)
    }
    for (const key of referenceKeys) {
      if (!localeKeys.has(key))
        errors.push(
          error(
            "LOCALE_KEY_MISSING",
            `${key} exists in ${referenceLocale} but not ${locale}`,
            "locales",
            key
          )
        )
    }
    for (const key of localeKeys) {
      if (!referenceKeys.has(key))
        errors.push(
          error(
            "LOCALE_KEY_ORPHAN",
            `${key} exists in ${locale} but not ${referenceLocale}`,
            "locales",
            key
          )
        )
    }
  }

  const allKeys = unique([
    ...referenceKeys,
    ...locales.slice(1).flatMap((locale) => [...allNamespaceKeys(info, locale)]),
  ])
  for (const key of allKeys) {
    const values = locales.map((locale) => {
      const { namespace, path: resourcePath } = splitTranslationKey(key)
      return info[locale]?.[namespace]?.values.get(resourcePath)
    })
    const present = values.filter((value) => value !== undefined)
    if (present.length >= 2) {
      const expected = placeholderNames(present[0])
      for (const value of present.slice(1)) {
        if (JSON.stringify(expected) !== JSON.stringify(placeholderNames(value))) {
          errors.push(
            error(
              "PLACEHOLDER_MISMATCH",
              `${key} uses different interpolation variables between locales`,
              "locales",
              key
            )
          )
          break
        }
        if (
          JSON.stringify(placeholderSpecs(present[0])) !== JSON.stringify(placeholderSpecs(value))
        ) {
          errors.push(
            error(
              "FORMAT_SPEC_MISMATCH",
              `${key} uses different date/number interpolation formats between locales`,
              "locales",
              key
            )
          )
          break
        }
      }
    }
  }

  const pluralGroups = new Map()
  for (const locale of locales) {
    for (const [namespace, resource] of Object.entries(info[locale] ?? {})) {
      for (const key of resource.values.keys()) {
        const match = key.match(PLURAL_SUFFIX)
        if (!match) continue
        const base = `${namespace}:${key.slice(0, -match[0].length)}`
        if (!pluralGroups.has(base)) pluralGroups.set(base, {})
        const group = pluralGroups.get(base)
        if (!group[locale]) group[locale] = new Set()
        group[locale].add(match[1])
      }
    }
  }
  for (const [base, byLocale] of pluralGroups.entries()) {
    const signatures = locales.map((locale) =>
      [...(byLocale[locale] ?? new Set())].sort().join(",")
    )
    if (new Set(signatures).size > 1)
      errors.push(
        error(
          "PLURAL_VARIANTS_MISMATCH",
          `${base} has inconsistent plural variants (${signatures.join(" vs ")})`,
          "locales",
          base
        )
      )
  }
  return { errors, locales, info }
}

function scanLanguagePersistence(source, filePath = "src/contexts/LanguageContext.tsx") {
  const errors = []
  const hasWindowGuard = /typeof\s+window\s*(?:===|!==)\s*["']undefined["']/u.test(source)
  if (/\bnavigator\.(?:language|languages)\b/u.test(source) && !hasWindowGuard) {
    errors.push(
      error(
        "HYDRATION_UNSAFE_LANGUAGE_READ",
        "navigator language must not be read during SSR render",
        filePath
      )
    )
  }
  if (
    /localStorage\.(?:getItem|setItem)\s*\(/u.test(source) &&
    !hasWindowGuard &&
    !/useEffect\s*\(/u.test(source)
  ) {
    errors.push(
      error(
        "LANGUAGE_STORAGE_DURING_RENDER",
        "Language storage access must be guarded and persisted from a browser effect",
        filePath
      )
    )
  }
  if (
    !/ue:language/u.test(source) ||
    !/localStorage\.setItem\s*\(/u.test(source) ||
    !/useEffect\s*\(/u.test(source)
  ) {
    errors.push(
      error(
        "LANGUAGE_PERSISTENCE_MISSING",
        "Language selection must persist ue:language from a browser effect",
        filePath
      )
    )
  }
  if (/useState\s*\(\s*\(?.*navigator\.(?:language|languages)/su.test(source)) {
    errors.push(
      error(
        "HYDRATION_UNSAFE_LANGUAGE_READ",
        "useState must use a deterministic SSR-safe language initializer",
        filePath
      )
    )
  }
  return { errors }
}

async function listFiles(directory, predicate) {
  const entries = await readdir(directory, { withFileTypes: true })
  const files = []
  for (const entry of entries) {
    if (entry.isDirectory()) {
      if (!SKIPPED_DIRECTORIES.has(entry.name))
        files.push(...(await listFiles(path.join(directory, entry.name), predicate)))
      continue
    }
    const fullPath = path.join(directory, entry.name)
    if (predicate(fullPath, entry.name)) files.push(fullPath)
  }
  return files
}

async function loadLocaleCatalogs(localeRoot = DEFAULT_LOCALE_ROOT, locales = ["en", "ru"]) {
  const catalogues = {}
  for (const locale of locales) {
    const directory = path.join(localeRoot, locale)
    const resources = {}
    if (!existsSync(directory)) {
      catalogues[locale] = resources
      continue
    }
    const files = await listFiles(
      directory,
      (filePath) => path.extname(filePath).toLowerCase() === ".json"
    )
    for (const filePath of files) {
      const namespace = path.basename(filePath, ".json")
      resources[namespace] = JSON.parse(await readFile(filePath, "utf8"))
    }
    catalogues[locale] = resources
  }
  return catalogues
}

function loadDynamicRegistry(registryFile = DEFAULT_REGISTRY_FILE) {
  if (!existsSync(registryFile)) return {}
  const source = readFileSync(registryFile, "utf8")
  const registry = {}
  const entryPattern =
    /^\s*(?:(?<quote>["'])(?<quoted>(?:(?!\k<quote>|\\).|\\.)*)\k<quote>|(?<bare>[A-Za-z_$][\w$.-]*))\s*:\s*\[([^\]]*)\]/gmu
  for (const match of source.matchAll(entryPattern)) {
    const rawKey = match.groups?.quoted ?? match.groups?.bare
    if (!rawKey) continue
    const key = rawKey.replaceAll('\\"', '"').replaceAll("\\'", "'").replaceAll("\\n", "\n")
    const values = [...match[4].matchAll(/(["'])(?:(?!\1|\\).|\\.)*\1/gu)].map((value) =>
      value[0].slice(1, -1).replaceAll('\\"', '"').replaceAll("\\'", "'")
    )
    registry[key] = values
  }
  return registry
}

async function scanRepository(options = {}) {
  const sourceRoot = options.sourceRoot ?? DEFAULT_SOURCE_ROOT
  const localeRoot = options.localeRoot ?? DEFAULT_LOCALE_ROOT
  const catalogues =
    options.catalogs ?? (await loadLocaleCatalogs(localeRoot, options.locales ?? ["en", "ru"]))
  const localeReport = scanLocaleCatalogs(catalogues)
  const catalogInfo = localeReport.info
  const dynamicRegistry =
    options.dynamicRegistry ?? loadDynamicRegistry(options.registryFile ?? DEFAULT_REGISTRY_FILE)
  const files = await listFiles(sourceRoot, (filePath, basename) => {
    const extension = path.extname(filePath).toLowerCase()
    if (!SOURCE_EXTENSIONS.has(extension)) return false
    return !SKIPPED_FILE_PATTERNS.some((pattern) => pattern.test(basename))
  })
  const reports = []
  for (const filePath of files) {
    const source = await readFile(filePath, "utf8")
    const relative = path.relative(FRONTEND_ROOT, filePath).replaceAll(path.sep, "/")
    reports.push(
      scanSource(source, { filePath: relative, catalogues, catalogInfo, dynamicRegistry })
    )
  }
  const languageFile = path.join(sourceRoot, "contexts", "LanguageContext.tsx")
  if (existsSync(languageFile)) {
    const relative = path.relative(FRONTEND_ROOT, languageFile).replaceAll(path.sep, "/")
    const languageReport = scanLanguagePersistence(await readFile(languageFile, "utf8"), relative)
    reports.push(languageReport)
  }
  const errors = [...localeReport.errors, ...reports.flatMap((report) => report.errors)]
  const references = reports.flatMap((report) => report.references ?? [])
  const dynamicReferences = reports.flatMap((report) => report.dynamicReferences ?? [])
  return {
    ok: errors.length === 0,
    errors,
    references,
    dynamicReferences,
    files,
    catalogs: catalogues,
    localeReport,
    dynamicRegistry,
  }
}

function formatErrors(errors) {
  return errors
    .map((entry) => {
      const location = entry.filePath
        ? `${entry.filePath}${entry.line ? `:${entry.line}${entry.column ? `:${entry.column}` : ""}` : ""}`
        : "locales"
      return `[${entry.code}] ${location}: ${entry.message}`
    })
    .join("\n")
}

export {
  flattenLocale,
  loadDynamicRegistry,
  loadLocaleCatalogs,
  scanLanguagePersistence,
  scanLocaleCatalogs,
  scanRepository,
  scanSource,
}

if (
  import.meta.url === `file://${process.argv[1]?.replaceAll("\\", "/")}` ||
  process.argv[1]?.endsWith("i18n-scanner.mjs")
) {
  const report = await scanRepository()
  if (!report.ok) {
    console.error(formatErrors(report.errors))
    process.exitCode = 1
  } else {
    console.log(
      `i18n check passed (${report.references.length} static references, ${report.dynamicReferences.length} dynamic references)`
    )
  }
}
