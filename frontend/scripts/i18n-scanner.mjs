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
const REPOSITORY_ROOT = path.resolve(FRONTEND_ROOT, "..")
const DEFAULT_SOURCE_ROOT = path.join(FRONTEND_ROOT, "src")
const DEFAULT_LOCALE_ROOT = path.join(FRONTEND_ROOT, "src", "i18n", "locales")
const DEFAULT_REGISTRY_FILE = path.join(FRONTEND_ROOT, "src", "i18n", "registry.ts")
const DEFAULT_BACKEND_DICTIONARY_FILE = path.join(
  REPOSITORY_ROOT,
  "app",
  "core",
  "localization",
  "dictionary.py"
)
const DEFAULT_BACKEND_TEMPLATE_FILES = [
  path.join(REPOSITORY_ROOT, "app", "utils", "email.py"),
  path.join(REPOSITORY_ROOT, "app", "services", "notification_templates.py"),
]
const DEFAULT_BACKEND_ROOT = path.join(REPOSITORY_ROOT, "app")
const DEFAULT_BACKEND_DYNAMIC_REGISTRY = {
  "stats.period.${query.period_key}": ["stats.period.30d", "stats.period.90d", "stats.period.180d"],
  "password.class.${class_name}": [
    "password.class.uppercase",
    "password.class.lowercase",
    "password.class.digit",
    "password.class.symbol",
  ],
  parity_key: ["schedule.ics.description.parity_odd", "schedule.ics.description.parity_even"],
  detail_key: [
    "errors.files.unsupported_type",
    "errors.files.content_type_mismatch",
    "errors.files.too_large",
    "errors.not_found",
    "errors.already_exists",
    "errors.forbidden",
    "errors.csrf.mismatch",
    "errors.config.payload_too_large",
    "errors.config.invalid_content_length",
    "errors.rate_limit.generic",
    "errors.schedule.conflict",
  ],
  message_key: [
    "errors.forbidden",
    "errors.unauthorized",
    "errors.not_found",
    "errors.already_exists",
    "errors.common.bad_request",
    "errors.rate_limit.generic",
    "errors.auth.mfa_step_up_required",
    "errors.users.create_failed",
    "errors.sessions.signing_key_missing",
    "errors.spotify.rate_limited",
    "errors.push.not_configured",
  ],
  title_key: [
    "titles.bad_request",
    "titles.unauthorized",
    "titles.forbidden",
    "titles.not_found",
    "titles.conflict",
    "titles.method_not_allowed",
    "titles.validation_error",
    "titles.rate_limit_exceeded",
    "titles.internal_server_error",
    "titles.http_error",
  ],
  translation_key: [
    "schedule.lesson.type.lecture",
    "schedule.lesson.type.practice",
    "schedule.lesson.type.lab",
    "schedule.lesson.type.seminar",
    "schedule.lesson.type.consultation",
  ],
}

const SOURCE_EXTENSIONS = new Set([".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"])
const SKIPPED_DIRECTORIES = new Set([
  ".git",
  ".next",
  "coverage",
  "dist",
  "generated",
  "node_modules",
  ".storybook",
  "__pycache__",
  "test",
  "tests",
  "__tests__",
  "vendor",
  ".storybook",
])
const SKIPPED_FILE_PATTERNS = [/(?:^|[._-])(test|spec|stories?)(?:[._-]|$)/iu, /^setupTests\./iu]
const SCOPE_EXCLUDED_DIRECTORIES = new Set([
  "test",
  "tests",
  "__tests__",
  "generated",
  "vendor",
  "coverage",
  "dist",
  "node_modules",
  ".storybook",
])
const USER_FACING_ATTRIBUTES = new Set([
  "alt",
  "aria-label",
  // React component props are commonly camel-cased even when they map to a
  // kebab-cased DOM attribute (for example, Skeleton's `ariaLabel`).
  "ariaLabel",
  "aria-description",
  "aria-valuetext",
  "label",
  "placeholder",
  "title",
  "description",
])
const USER_FACING_DEFAULT_IDENTIFIERS = new Set([
  "alt",
  "ariaLabel",
  "description",
  "label",
  "placeholder",
  "title",
])
const NON_USER_FACING_TAGS = new Set(["script", "style", "code", "pre"])
const PLURAL_SUFFIX = /_(zero|one|two|few|many|other)$/u
const PLACEHOLDER = /\{\{\s*-?\s*([\w.-]+)(?:\s*,\s*([^}]+?))?\s*\}\}/gu
const PYTHON_PLACEHOLDER = /(?<!\{)\{([A-Za-z_]\w*(?:\.[\w]+)*)(?:![rsa])?(?::([^{}]*))?\}(?!\})/gu
const PYTHON_ESCAPE = /\\([\\nrt"'])/gu
const PYTHON_ESCAPE_MAP = Object.freeze({
  "\\": "\\",
  n: "\n",
  r: "\r",
  t: "\t",
  '"': '"',
  "'": "'",
})

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

function pythonPlaceholderNames(value) {
  const names = []
  const text = typeof value === "string" ? value : ""
  for (const match of text.matchAll(PYTHON_PLACEHOLDER)) names.push(match[1])
  return unique(names).sort()
}

function pythonPlaceholderSpecs(value) {
  const specs = new Map()
  const text = typeof value === "string" ? value : ""
  for (const match of text.matchAll(PYTHON_PLACEHOLDER)) {
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
    if (node.type === "AssignmentPattern") {
      const name = node.left?.type === "Identifier" ? node.left.name : undefined
      const value = nodeString(node.right)
      if (
        name &&
        USER_FACING_DEFAULT_IDENTIFIERS.has(name) &&
        value &&
        /\p{L}/u.test(value) &&
        !isTechnicalLiteral(value, filePath)
      ) {
        errors.push(
          error(
            "RAW_USER_FACING_LITERAL",
            `Raw default value for user-facing ${name} must use a translation key`,
            node.right,
            value
          )
        )
      }
      return
    }
    if (node.type === "CallExpression" && isTranslationCallee(node.callee)) {
      const fallback = node.arguments?.[1]
      const fallbackValue = nodeString(fallback)
      if (
        fallbackValue &&
        /\p{L}/u.test(fallbackValue) &&
        !isTechnicalLiteral(fallbackValue, filePath)
      ) {
        errors.push(
          error(
            "RAW_USER_FACING_LITERAL",
            "Raw translation fallback must use a catalogue key",
            fallback,
            fallbackValue
          )
        )
      } else if (fallback?.type === "ObjectExpression") {
        for (const property of fallback.properties ?? []) {
          if (property.type !== "ObjectProperty" && property.type !== "ObjectMethod") continue
          const propertyName =
            property.key?.type === "Identifier" ? property.key.name : nodeString(property.key)
          if (propertyName !== "defaultValue") continue
          const defaultValue = nodeString(property.value)
          if (
            defaultValue &&
            /\p{L}/u.test(defaultValue) &&
            !isTechnicalLiteral(defaultValue, filePath)
          ) {
            errors.push(
              error(
                "RAW_USER_FACING_LITERAL",
                "Raw translation defaultValue must use a catalogue key",
                property.value,
                defaultValue
              )
            )
          }
        }
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

/**
 * Validate the dynamic-key contract before resolving any source reference.
 *
 * A registry is intentionally a finite map from an expression pattern to
 * concrete catalogue keys.  Wildcards and empty/non-string entries would turn
 * the registry into an allow-all escape hatch, so they are rejected even when
 * a particular expression is not referenced by the current source tree.
 */
function validateDynamicRegistry(dynamicRegistry = {}) {
  const errors = []
  if (!isObject(dynamicRegistry)) {
    errors.push(
      error(
        "DYNAMIC_REGISTRY_INVALID",
        "Dynamic translation registry must be an object of finite string arrays",
        "registry"
      )
    )
    return { ok: false, errors }
  }

  for (const [pattern, values] of Object.entries(dynamicRegistry)) {
    if (!pattern.trim()) {
      errors.push(
        error("DYNAMIC_REGISTRY_INVALID", "Dynamic registry patterns must not be empty", "registry")
      )
    }
    if (pattern.includes("*")) {
      errors.push(
        error(
          "DYNAMIC_REGISTRY_WILDCARD",
          `Dynamic registry pattern ${pattern} must describe one finite expression`,
          "registry",
          pattern
        )
      )
    }
    if (!Array.isArray(values)) {
      errors.push(
        error(
          "DYNAMIC_REGISTRY_VALUE_INVALID",
          `Dynamic registry entry ${pattern} must be an array`,
          "registry",
          pattern
        )
      )
      continue
    }
    if (values.length === 0) {
      errors.push(
        error(
          "DYNAMIC_REGISTRY_EMPTY",
          `Dynamic registry entry ${pattern} must contain at least one concrete key`,
          "registry",
          pattern
        )
      )
    }
    for (const value of values) {
      if (typeof value !== "string" || !value.trim()) {
        errors.push(
          error(
            "DYNAMIC_REGISTRY_VALUE_INVALID",
            `Dynamic registry entry ${pattern} contains a non-string key`,
            "registry",
            pattern
          )
        )
        continue
      }
      if (value.includes("*")) {
        errors.push(
          error(
            "DYNAMIC_REGISTRY_WILDCARD",
            `Dynamic registry key ${value} must be concrete; wildcards are forbidden`,
            "registry",
            pattern
          )
        )
      }
    }
  }
  return { ok: errors.length === 0, errors }
}

function normalizeScopePath(filePath) {
  return String(filePath).replaceAll("\\", "/").replace(/^\.\//u, "")
}

function isScopeExcluded(filePath) {
  const normalized = normalizeScopePath(filePath)
  const basename = normalized.slice(normalized.lastIndexOf("/") + 1)
  const segments = normalized.split("/")
  return (
    segments.some((segment) => SCOPE_EXCLUDED_DIRECTORIES.has(segment)) ||
    SKIPPED_FILE_PATTERNS.some((pattern) => pattern.test(basename))
  )
}

/**
 * Keep the product-string scan explicit about its scope.  Tests, generated
 * clients and vendored sources are intentionally excluded from product
 * findings, but are returned as a separate machine-readable list so a caller
 * cannot mistake that exclusion for an unscanned path.
 */
function scanScopeContract(filePaths = []) {
  const included = []
  const excluded = []
  for (const filePath of filePaths) {
    const normalized = normalizeScopePath(filePath)
    if (isScopeExcluded(normalized)) excluded.push(normalized)
    else included.push(normalized)
  }
  return {
    ok: true,
    errors: [],
    included,
    excluded,
    excludedDirectories: [...SCOPE_EXCLUDED_DIRECTORIES].sort(),
    excludedFilePatterns: SKIPPED_FILE_PATTERNS.map((pattern) => pattern.toString()),
  }
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

function decodePythonEscapes(value) {
  return value.replace(PYTHON_ESCAPE, (_match, escaped) => PYTHON_ESCAPE_MAP[escaped])
}

function pythonStringParts(value) {
  const parts = []
  const stringPattern =
    /(?<prefix>[rubfRUBF]*)(?<quote>"""|'''|"|')(?<body>(?:\\.|(?!\k<quote>)[\s\S])*?)\k<quote>/gu
  for (const match of value.matchAll(stringPattern)) {
    const body = match.groups?.body ?? ""
    parts.push(decodePythonEscapes(body))
  }
  return parts
}

function balancedPythonExpression(source, start, open = "{", close = "}") {
  let depth = 0
  let quote = ""
  let triple = false
  for (let index = start; index < source.length; index += 1) {
    const character = source[index]
    const next = source.slice(index, index + 3)
    if (quote) {
      if (character === "\\") {
        index += 1
        continue
      }
      if (triple ? next === quote.repeat(3) : character === quote) {
        if (triple) index += 2
        quote = ""
        triple = false
      }
      continue
    }
    if (character === '"' || character === "'") {
      if (next === character.repeat(3)) {
        quote = character
        triple = true
        index += 2
      } else {
        quote = character
      }
      continue
    }
    if (character === open) depth += 1
    if (character === close) {
      depth -= 1
      if (depth === 0) return source.slice(start, index + 1)
    }
  }
  return source.slice(start)
}

function pythonLocaleValues(block) {
  const values = {}
  const localePattern = /(?<quote>["'])(?<locale>[A-Za-z][A-Za-z0-9_-]*)\k<quote>\s*:/gu
  for (const match of block.matchAll(localePattern)) {
    const valueStart = (match.index ?? 0) + match[0].length
    let depth = 0
    let quote = ""
    let triple = false
    let end = block.length
    for (let index = valueStart; index < block.length; index += 1) {
      const character = block[index]
      const next = block.slice(index, index + 3)
      if (quote) {
        if (character === "\\") {
          index += 1
          continue
        }
        if (triple ? next === quote.repeat(3) : character === quote) {
          if (triple) index += 2
          quote = ""
          triple = false
        }
        continue
      }
      if (character === '"' || character === "'") {
        if (next === character.repeat(3)) {
          quote = character
          triple = true
          index += 2
        } else {
          quote = character
        }
        continue
      }
      if ("([{".includes(character)) depth += 1
      else if (")]}".includes(character)) depth = Math.max(depth - 1, 0)
      else if ((character === "," || character === "\n") && depth === 0) {
        end = index
        break
      }
    }
    values[match.groups.locale] = pythonStringParts(block.slice(valueStart, end)).join("")
  }
  return values
}

/**
 * Parse the deliberately data-only Python translation dictionary without
 * importing application code.  The parser accepts ordinary Python quoted
 * strings, adjacent strings in parentheses, and both one-line and multiline
 * locale entries.  It never evaluates arbitrary Python expressions.
 */
function parsePythonTranslationCatalog(source) {
  const catalog = {}
  const keyPattern = /^ {4}(?<quote>["'])(?<key>(?:\\.|(?!\k<quote>)[\s\S])*?)\k<quote>\s*:\s*/gmu
  for (const match of source.matchAll(keyPattern)) {
    const valueStart = (match.index ?? 0) + match[0].length
    const braceStart = source.indexOf("{", valueStart)
    if (braceStart === -1) continue
    const block = balancedPythonExpression(source, braceStart)
    const key = decodePythonEscapes(match.groups?.key ?? "")
    catalog[key] = pythonLocaleValues(block)
  }
  return catalog
}

function scanBackendCatalog(catalog = {}, locales = ["en", "ru"]) {
  const errors = []
  for (const [key, values] of Object.entries(catalog)) {
    if (!isObject(values)) {
      errors.push(
        error(
          "BACKEND_CATALOG_ENTRY_INVALID",
          `Backend translation ${key} must be a locale map`,
          "backend",
          key
        )
      )
      continue
    }
    for (const locale of Object.keys(values)) {
      if (!locales.includes(locale)) {
        errors.push(
          error(
            "BACKEND_LOCALE_ORPHAN",
            `Backend translation ${key} contains unsupported locale ${locale}`,
            "backend",
            key
          )
        )
      }
    }
    for (const locale of locales) {
      if (typeof values[locale] !== "string" || !values[locale].trim()) {
        errors.push(
          error(
            "BACKEND_LOCALE_MISSING",
            `Backend translation ${key} is missing a non-empty ${locale} value`,
            "backend",
            key
          )
        )
      }
    }
    const present = locales
      .map((locale) => values[locale])
      .filter((value) => typeof value === "string")
    if (present.length >= 2) {
      const expected = pythonPlaceholderNames(present[0])
      for (const value of present.slice(1)) {
        if (JSON.stringify(expected) !== JSON.stringify(pythonPlaceholderNames(value))) {
          errors.push(
            error(
              "PLACEHOLDER_MISMATCH",
              `Backend translation ${key} uses different interpolation variables between locales`,
              "backend",
              key
            )
          )
          break
        }
        if (
          JSON.stringify(pythonPlaceholderSpecs(present[0])) !==
          JSON.stringify(pythonPlaceholderSpecs(value))
        ) {
          errors.push(
            error(
              "FORMAT_SPEC_MISMATCH",
              `Backend translation ${key} uses different date/number interpolation formats`,
              "backend",
              key
            )
          )
          break
        }
      }
    }
  }
  return { ok: errors.length === 0, errors, locales, catalog }
}

function pythonCallFirstArgument(source, start) {
  let index = start
  while (/\s/u.test(source[index] ?? "")) index += 1
  const argumentStart = index
  let depth = 0
  let quote = ""
  let triple = false
  for (; index < source.length; index += 1) {
    const character = source[index]
    if (quote) {
      if (character === "\\") {
        index += 1
        continue
      }
      if (triple ? source.slice(index, index + 3) === quote.repeat(3) : character === quote) {
        if (triple) index += 2
        quote = ""
        triple = false
      }
      continue
    }
    if (character === '"' || character === "'") {
      if (source.slice(index, index + 3) === character.repeat(3)) {
        quote = character
        triple = true
        index += 2
      } else {
        quote = character
      }
      continue
    }
    if ("([{".includes(character)) depth += 1
    else if (")]}".includes(character)) {
      if (depth === 0) break
      depth -= 1
    } else if (character === "," && depth === 0) break
  }
  const end = index
  const raw = source.slice(argumentStart, end).trim()
  if (!raw) return { kind: "dynamic", pattern: "<dynamic>", end }

  // A simple quoted token is static only when the complete first argument is
  // that token.  Expressions such as `"a" if cond else "b"` and
  // `"prefix." + suffix` must stay dynamic and go through the finite registry.
  const prefixMatch = raw.match(/^(?<prefix>[fFrRuUbB]*)(?<quote>"""|'''|"|')/u)
  if (prefixMatch) {
    const prefix = prefixMatch.groups?.prefix ?? ""
    const delimiter = prefixMatch.groups?.quote ?? '"'
    const bodyStart = prefix.length + delimiter.length
    let tokenEnd = bodyStart
    let escaped = false
    while (tokenEnd < raw.length) {
      const character = raw[tokenEnd]
      if (escaped) {
        escaped = false
        tokenEnd += 1
        continue
      }
      if (character === "\\") {
        escaped = true
        tokenEnd += 1
        continue
      }
      if (raw.slice(tokenEnd, tokenEnd + delimiter.length) === delimiter) {
        tokenEnd += delimiter.length
        break
      }
      tokenEnd += 1
    }
    if (tokenEnd === raw.length) {
      const body = raw.slice(bodyStart, raw.length - delimiter.length)
      if (prefix.toLowerCase().includes("f")) {
        return {
          kind: "dynamic",
          pattern: body.replace(
            /\{([^{}]+)\}/gu,
            (_match, expression) => `\${${expression.trim()}}`
          ),
          end,
        }
      }
      return { kind: "static", key: pythonStringParts(raw).join(""), end }
    }
  }

  return { kind: "dynamic", pattern: raw, end }
}

function scanBackendSource(source, options = {}) {
  const filePath = options.filePath ?? "backend.py"
  const catalog = options.catalog ?? {}
  const dynamicRegistry = options.dynamicRegistry ?? {}
  const errors = []
  const references = []
  const dynamicReferences = []
  const callPattern = /\btranslate\s*\(/gu
  for (const match of source.matchAll(callPattern)) {
    const callIndex = match.index ?? 0
    const lineStart = source.lastIndexOf("\n", callIndex - 1) + 1
    const linePrefix = source.slice(lineStart, callIndex)
    if (linePrefix.trimStart().startsWith("#") || /^\s*def\s+$/u.test(linePrefix)) continue
    const argument = pythonCallFirstArgument(source, callIndex + match[0].length)
    if (argument.kind === "dynamic") {
      dynamicReferences.push({ pattern: argument.pattern, filePath, registered: false })
      const registered = registryLookup(argument.pattern, dynamicRegistry)
      if (!registered) {
        errors.push(
          error(
            "DYNAMIC_KEY_UNREGISTERED",
            `Dynamic translation key ${argument.pattern} must have a finite registry entry`,
            filePath,
            argument.pattern
          )
        )
        continue
      }
      dynamicReferences[dynamicReferences.length - 1].registered = true
      for (const concreteKey of registered) {
        if (typeof concreteKey !== "string" || concreteKey.includes("*")) {
          errors.push(
            error(
              "DYNAMIC_KEY_WILDCARD",
              `Dynamic translation registry entry ${String(concreteKey)} must be concrete`,
              filePath,
              argument.pattern
            )
          )
          continue
        }
        if (!catalog[concreteKey]) {
          errors.push(
            error(
              "TRANSLATION_KEY_MISSING",
              `Backend translation key ${concreteKey} is missing from the catalogue`,
              filePath,
              concreteKey
            )
          )
          continue
        }
        references.push({ key: concreteKey, dynamic: true, filePath })
      }
      continue
    }
    const key = argument.key.trim()
    references.push({ key, dynamic: false, filePath })
    const values = catalog[key]
    if (!values) {
      errors.push(
        error(
          "TRANSLATION_KEY_MISSING",
          `Backend translation key ${key} is missing from the catalogue`,
          filePath,
          key
        )
      )
      continue
    }
    const requiredLocales = ["en", "ru"]
    for (const locale of requiredLocales) {
      if (typeof values[locale] !== "string" || !values[locale].trim()) {
        errors.push(
          error(
            "BACKEND_LOCALE_MISSING",
            `Backend translation ${key} is missing a non-empty ${locale} value`,
            filePath,
            key
          )
        )
      }
    }
    const locales = requiredLocales
      .map((locale) => values[locale])
      .filter((value) => typeof value === "string")
    if (
      locales.length >= 2 &&
      JSON.stringify(pythonPlaceholderNames(locales[0])) !==
        JSON.stringify(pythonPlaceholderNames(locales[1]))
    ) {
      errors.push(
        error(
          "PLACEHOLDER_MISMATCH",
          `Backend translation ${key} uses different interpolation variables between locales`,
          filePath,
          key
        )
      )
    } else if (
      locales.length >= 2 &&
      JSON.stringify(pythonPlaceholderSpecs(locales[0])) !==
        JSON.stringify(pythonPlaceholderSpecs(locales[1]))
    ) {
      errors.push(
        error(
          "FORMAT_SPEC_MISMATCH",
          `Backend translation ${key} uses different date/number interpolation formats`,
          filePath,
          key
        )
      )
    }
  }
  const rawAssignment =
    /^(?<indent>\s*)(?<name>subject|heading|greeting|body|action|title|message|description|label|text)\s*=\s*(?<quote>["'])(?<value>(?:\\.|(?!\k<quote>)[^\n])*?)\k<quote>\s*$/gmu
  for (const match of source.matchAll(rawAssignment)) {
    const value = match.groups?.value ?? ""
    if (/\p{L}/u.test(value) && !isTechnicalLiteral(value, filePath)) {
      errors.push(
        error(
          "RAW_USER_FACING_LITERAL",
          `Raw backend user-facing ${match.groups?.name ?? "text"} must use a translation key`,
          filePath
        )
      )
    }
  }
  return { ok: errors.length === 0, errors, references, dynamicReferences }
}

async function loadBackendTranslationCatalog(dictionaryFile = DEFAULT_BACKEND_DICTIONARY_FILE) {
  if (!existsSync(dictionaryFile)) return {}
  return parsePythonTranslationCatalog(await readFile(dictionaryFile, "utf8"))
}

async function listBackendTranslationFiles(backendRoot = DEFAULT_BACKEND_ROOT) {
  const candidates = await listFiles(
    backendRoot,
    (filePath) => path.extname(filePath).toLowerCase() === ".py"
  )
  const files = []
  for (const filePath of candidates) {
    const source = await readFile(filePath, "utf8")
    if (/\btranslate\s*\(/u.test(source)) files.push(filePath)
  }
  return files.sort((left, right) => left.localeCompare(right))
}

async function scanBackendRepository(options = {}) {
  const dictionaryFile = options.backendDictionaryFile ?? DEFAULT_BACKEND_DICTIONARY_FILE
  const catalog = options.backendCatalog ?? (await loadBackendTranslationCatalog(dictionaryFile))
  const catalogReport = scanBackendCatalog(catalog)
  const dynamicRegistry = options.backendDynamicRegistry ?? DEFAULT_BACKEND_DYNAMIC_REGISTRY
  const registryReport = validateDynamicRegistry(dynamicRegistry)
  const configuredFiles = options.backendTemplateFiles
    ? options.backendTemplateFiles
    : await listBackendTranslationFiles(options.backendRoot ?? DEFAULT_BACKEND_ROOT)
  const files = configuredFiles.length > 0 ? configuredFiles : DEFAULT_BACKEND_TEMPLATE_FILES
  const reports = []
  for (const configuredPath of files) {
    const filePath = path.isAbsolute(configuredPath)
      ? configuredPath
      : path.resolve(REPOSITORY_ROOT, configuredPath)
    if (!existsSync(filePath)) {
      reports.push({
        ok: false,
        errors: [
          error(
            "BACKEND_TEMPLATE_MISSING",
            `Backend localization template ${configuredPath} does not exist`,
            String(configuredPath)
          ),
        ],
        references: [],
        dynamicReferences: [],
      })
      continue
    }
    const relativePath = path.relative(REPOSITORY_ROOT, filePath).replaceAll(path.sep, "/")
    reports.push(
      scanBackendSource(await readFile(filePath, "utf8"), {
        filePath: relativePath,
        catalog,
        dynamicRegistry,
      })
    )
  }
  const errors = [
    ...catalogReport.errors,
    ...registryReport.errors,
    ...reports.flatMap((report) => report.errors),
  ]
  return {
    ok: errors.length === 0,
    errors,
    references: reports.flatMap((report) => report.references),
    dynamicReferences: reports.flatMap((report) => report.dynamicReferences),
    files,
    catalog,
    catalogReport,
    registryReport,
    dynamicRegistry,
  }
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

// The product scan intentionally skips tests/generated/vendor sources, but the
// machine-readable scope report must prove that those paths were considered.
// Walk the source tree once more without applying product exclusions so the
// report can list them explicitly.  Keep only build/dependency directories out
// of this inventory; their names and exclusion rules remain visible in the
// returned contract.
const SCOPE_TRAVERSAL_IGNORED_DIRECTORIES = new Set([
  ".git",
  ".next",
  "coverage",
  "dist",
  "node_modules",
])

async function listScopeCandidates(directory, predicate) {
  const entries = await readdir(directory, { withFileTypes: true })
  const files = []
  for (const entry of entries) {
    const fullPath = path.join(directory, entry.name)
    if (entry.isDirectory()) {
      if (!SCOPE_TRAVERSAL_IGNORED_DIRECTORIES.has(entry.name)) {
        files.push(...(await listScopeCandidates(fullPath, predicate)))
      }
      continue
    }
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
  const scopeCandidates = await listScopeCandidates(sourceRoot, (filePath) => {
    const extension = path.extname(filePath).toLowerCase()
    return SOURCE_EXTENSIONS.has(extension)
  })
  const files = scopeCandidates.filter((filePath) => {
    const basename = path.basename(filePath)
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
  const registryReport = validateDynamicRegistry(dynamicRegistry)
  const scope = scanScopeContract(
    scopeCandidates.map((filePath) =>
      path.relative(FRONTEND_ROOT, filePath).replaceAll(path.sep, "/")
    )
  )
  const backendReport =
    options.includeBackend === false
      ? {
          ok: true,
          errors: [],
          references: [],
          dynamicReferences: [],
          files: [],
          catalog: {},
          catalogReport: { ok: true, errors: [], locales: ["en", "ru"], catalog: {} },
          registryReport: { ok: true, errors: [] },
          dynamicRegistry: {},
        }
      : await scanBackendRepository(options)
  const errors = [
    ...localeReport.errors,
    ...registryReport.errors,
    ...scope.errors,
    ...reports.flatMap((report) => report.errors),
    ...backendReport.errors,
  ]
  const references = [
    ...reports.flatMap((report) => report.references ?? []),
    ...backendReport.references,
  ]
  const dynamicReferences = [
    ...reports.flatMap((report) => report.dynamicReferences ?? []),
    ...backendReport.dynamicReferences,
  ]
  return {
    ok: errors.length === 0,
    errors,
    references,
    dynamicReferences,
    files,
    catalogs: catalogues,
    localeReport,
    registryReport,
    scope,
    backend: backendReport,
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

function machineReadableReport(report) {
  return {
    ok: report.ok,
    errors: report.errors,
    references: report.references,
    dynamicReferences: report.dynamicReferences,
    files: report.files,
    scope: report.scope,
    locale: {
      locales: report.localeReport?.locales ?? [],
      errors: report.localeReport?.errors ?? [],
    },
    registry: {
      errors: report.registryReport?.errors ?? [],
      entries: Object.keys(report.dynamicRegistry ?? {}).length,
    },
    backend: {
      ok: report.backend?.ok ?? true,
      errors: report.backend?.errors ?? [],
      references: report.backend?.references ?? [],
      dynamicReferences: report.backend?.dynamicReferences ?? [],
      files: report.backend?.files ?? [],
      catalogEntries: Object.keys(report.backend?.catalog ?? {}).length,
      registry: {
        errors: report.backend?.registryReport?.errors ?? [],
        entries: Object.keys(report.backend?.dynamicRegistry ?? {}).length,
      },
    },
  }
}

export {
  flattenLocale,
  loadDynamicRegistry,
  loadBackendTranslationCatalog,
  loadLocaleCatalogs,
  parsePythonTranslationCatalog,
  scanBackendCatalog,
  scanBackendRepository,
  scanBackendSource,
  scanLanguagePersistence,
  scanLocaleCatalogs,
  scanRepository,
  scanScopeContract,
  scanSource,
  machineReadableReport,
  validateDynamicRegistry,
}

if (
  import.meta.url === `file://${process.argv[1]?.replaceAll("\\", "/")}` ||
  process.argv[1]?.endsWith("i18n-scanner.mjs")
) {
  const report = await scanRepository()
  if (process.argv.includes("--json")) {
    console.log(JSON.stringify(machineReadableReport(report), null, 2))
    if (!report.ok) process.exitCode = 1
  } else if (!report.ok) {
    console.error(formatErrors(report.errors))
    process.exitCode = 1
  } else {
    console.log(
      `i18n check passed (${report.references.length} static references, ${report.dynamicReferences.length} dynamic references)`
    )
  }
}
