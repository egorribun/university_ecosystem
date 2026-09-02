import { readFile, readdir } from "node:fs/promises"
import path from "node:path"
import process from "node:process"
import { fileURLToPath } from "node:url"

import routePolicyConfig from "./lhci-route-policy-config.cjs"

export const LHCI_PUBLIC_SEO_MIN_SCORE = routePolicyConfig.publicSeoMinScore
export const LHCI_PUBLIC_SEO_PATH_PREFIXES = Object.freeze([
  ...routePolicyConfig.publicSeoPathPrefixes,
])
export const LHCI_NOT_FOUND_PATH_PREFIXES = Object.freeze([
  ...routePolicyConfig.notFoundPathPrefixes,
])
export const LHCI_PROTECTED_ROUTE_PREFIXES = Object.freeze([
  ...routePolicyConfig.protectedRoutePrefixes,
])
export const LHCI_DEFAULT_EXPECTED_PATHS = Object.freeze([...routePolicyConfig.defaultLhciPaths])

const MODULE_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")
const REPORT_FILE_PATTERN = /^lhr-.+\.json$/u

/**
 * Normalize a URL pathname for route-prefix comparisons.
 *
 * Query strings and fragments do not belong to a pathname.  A trailing slash
 * is insignificant for route policy, except for the root path itself.
 */
export function normalizeRoutePath(pathname) {
  if (typeof pathname !== "string" || pathname.length === 0) {
    throw new TypeError("Route pathname must be a non-empty string")
  }

  const withoutQuery = pathname.split(/[?#]/u, 1)[0]
  if (!withoutQuery.startsWith("/")) {
    throw new TypeError(`Route pathname must start with '/': ${pathname}`)
  }

  if (withoutQuery === "/") return "/"
  return withoutQuery.replace(/\/+$/u, "") || "/"
}

/**
 * Normalize a user-provided LHCI_URLS segment before it reaches Lighthouse.
 *
 * Workflow inputs are commonly supplied as route names (`404`) rather than
 * URL pathnames (`/404`). Lighthouse accepts the former in some collection
 * modes but can emit a finalUrl without a leading slash; that bypasses the
 * route-policy inventory. Canonicalize both forms at the collection boundary
 * so every downstream policy check observes a valid pathname.
 */
export function normalizeLhciPath(value) {
  if (typeof value !== "string") {
    throw new TypeError("LHCI route value must be a string")
  }
  const trimmed = value.trim()
  if (trimmed === "") return "/"
  const pathname = trimmed.startsWith("/") ? trimmed : `/${trimmed}`
  const normalized = normalizeRoutePath(pathname)
  // Keep an explicit trailing slash for the collection URL.  Prepared LHCI
  // shells live in `<route>/index.html`; preserving the caller's canonical
  // directory form avoids a production-server redirect before Lighthouse
  // starts tracing.  Route-policy comparisons continue to normalize this
  // presentation detail via normalizeRoutePath().
  return normalized === "/" || !pathname.endsWith("/") ? normalized : `${normalized}/`
}

function pathMatchesPrefix(pathname, prefix) {
  const normalizedPath = normalizeRoutePath(pathname)
  const normalizedPrefix = normalizeRoutePath(prefix)
  return normalizedPath === normalizedPrefix || normalizedPath.startsWith(`${normalizedPrefix}/`)
}

export function classifyLhciPath(pathname) {
  const normalizedPath = normalizeRoutePath(pathname)

  if (LHCI_NOT_FOUND_PATH_PREFIXES.some((prefix) => pathMatchesPrefix(normalizedPath, prefix))) {
    return "not-found"
  }
  if (LHCI_PUBLIC_SEO_PATH_PREFIXES.some((prefix) => pathMatchesPrefix(normalizedPath, prefix))) {
    return "public"
  }
  if (LHCI_PROTECTED_ROUTE_PREFIXES.some((prefix) => pathMatchesPrefix(normalizedPath, prefix))) {
    return "protected"
  }
  return "unknown"
}

function normalizeRobotsRule(rule) {
  if (typeof rule !== "string") return null
  const normalized = rule.trim().split(/[?#]/u, 1)[0]
  if (!normalized.startsWith("/") || normalized === "") return null
  if (normalized === "/") return "/"
  return normalized.replace(/\/+$/u, "") || "/"
}

/**
 * Parse only Disallow directives from the wildcard robots group.
 *
 * Rules belonging exclusively to another user-agent are deliberately ignored;
 * accepting those as proof of privacy would make the check unsound.  Unknown
 * robots syntax is retained as a non-matching rule, which fails closed when a
 * protected path is evaluated.
 */
export function parseRobotsDisallows(robotsText) {
  if (typeof robotsText !== "string") {
    throw new TypeError("robots.txt contents must be a string")
  }

  const groups = []
  let userAgents = []
  let disallows = []
  let groupHasDirective = false
  const flushGroup = () => {
    if (userAgents.length > 0) {
      groups.push({ userAgents, disallows })
    }
    userAgents = []
    disallows = []
    groupHasDirective = false
  }

  for (const rawLine of robotsText.split(/\r?\n/u)) {
    const line = rawLine.replace(/#.*$/u, "").trim()
    if (line === "") {
      flushGroup()
      continue
    }

    const separator = line.indexOf(":")
    if (separator < 0) {
      // A malformed non-empty line is still content in the current group.
      // Marking it prevents a later User-agent header from merging its rules
      // into the wildcard group and falsely proving a privacy directive.
      groupHasDirective = true
      continue
    }
    const directive = line.slice(0, separator).trim().toLowerCase()
    const value = line.slice(separator + 1).trim()

    if (directive === "user-agent") {
      // Multiple User-agent lines before the first directive are one group.
      // A new User-agent after any directive starts a new group even if a
      // blank separator was omitted. Tracking all directives (including
      // Allow/unknown ones) avoids merging an Allow-only wildcard group with
      // a later bot-specific Disallow and falsely proving privacy.
      if (groupHasDirective) flushGroup()
      if (value !== "") userAgents.push(value.toLowerCase())
      continue
    }
    groupHasDirective = true
    if (directive === "disallow" && value !== "") {
      disallows.push(value)
    }
  }
  flushGroup()

  const wildcardRules = groups
    .filter((group) => group.userAgents.includes("*"))
    .flatMap((group) => group.disallows.map(normalizeRobotsRule).filter(Boolean))

  if (!groups.some((group) => group.userAgents.includes("*"))) {
    throw new Error("robots.txt has no User-agent: * group")
  }
  return Object.freeze([...new Set(wildcardRules)])
}

export function robotsDisallowsPath(pathname, rules) {
  if (!Array.isArray(rules)) {
    throw new TypeError("robots rules must be an array")
  }
  const normalizedPath = normalizeRoutePath(pathname)
  return rules.some((rawRule) => {
    const rule = normalizeRobotsRule(rawRule)
    if (!rule) return false
    return rule === "/" || normalizedPath === rule || normalizedPath.startsWith(`${rule}/`)
  })
}

function parseReportUrl(report) {
  if (!report || typeof report !== "object" || typeof report.finalUrl !== "string") {
    throw new TypeError("Lighthouse report is missing a finalUrl")
  }
  let parsed
  try {
    parsed = new URL(report.finalUrl)
  } catch {
    throw new TypeError("Lighthouse finalUrl is not an absolute URL")
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new TypeError("Lighthouse finalUrl uses an unsupported protocol")
  }

  let requestedPath = null
  if (report.requestedUrl !== undefined) {
    let requested
    try {
      requested = new URL(report.requestedUrl)
    } catch {
      throw new TypeError("Lighthouse requestedUrl is not an absolute URL")
    }
    if (requested.protocol !== "http:" && requested.protocol !== "https:") {
      throw new TypeError("Lighthouse requestedUrl uses an unsupported protocol")
    }
    requestedPath = normalizeRoutePath(requested.pathname)
  }
  return {
    parsed,
    pathname: normalizeRoutePath(parsed.pathname),
    requestedPath,
  }
}

function getCrawlAudit(report) {
  const audit = report?.audits?.["is-crawlable"]
  if (!audit || typeof audit !== "object") return null
  return audit
}

function hasRobotsSource(audit, baseUrl) {
  const items = audit?.details?.items
  if (!Array.isArray(items)) return false

  let expectedOrigin
  try {
    expectedOrigin = new URL(baseUrl).origin
  } catch {
    return false
  }

  return items.some((item) => {
    const sourceUrl = item?.source?.url
    if (typeof sourceUrl !== "string") return false
    try {
      const parsed = new URL(sourceUrl, baseUrl)
      return (
        (parsed.protocol === "http:" || parsed.protocol === "https:") &&
        parsed.origin === expectedOrigin &&
        parsed.pathname === "/robots.txt"
      )
    } catch {
      return false
    }
  })
}

function reportLabel(report, index) {
  if (typeof report?.__lhciReportPath === "string") return report.__lhciReportPath
  if (typeof report?.finalUrl === "string") {
    try {
      const parsed = new URL(report.finalUrl)
      return `${parsed.origin}${parsed.pathname}`
    } catch {
      return "Lighthouse report with invalid finalUrl"
    }
  }
  return `report #${index + 1}`
}

function normalizeExpectedPath(value) {
  if (typeof value !== "string" || value.trim() === "") {
    throw new TypeError("Expected Lighthouse route inventory contains an invalid path")
  }
  const trimmed = value.trim()
  if (/^https?:\/\//iu.test(trimmed)) {
    let parsed
    try {
      parsed = new URL(trimmed)
    } catch {
      throw new TypeError("Expected Lighthouse route inventory contains an invalid URL")
    }
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      throw new TypeError("Expected Lighthouse route inventory contains an unsupported URL")
    }
    return normalizeRoutePath(parsed.pathname)
  }
  return normalizeRoutePath(trimmed)
}

function finiteScore(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

/**
 * Validate route intent independently of LHCI's category assertions.
 *
 * Public routes must remain crawlable and meet the SEO floor.  Protected
 * routes must be blocked by the wildcard robots policy, and Lighthouse must
 * attribute that block to robots.txt rather than an unrelated meta directive.
 * Any route outside the explicit inventory is an error, preventing silently
 * ungoverned pages from entering the quality artifact.
 */
export function evaluateLhciRoutePolicy(reports, { robotsText, expectedPaths, expectedRuns } = {}) {
  const violations = []
  const results = []
  let robotsRules = []
  let expected = []

  if (!Array.isArray(expectedPaths) || expectedPaths.length === 0) {
    violations.push("expected Lighthouse route inventory is missing")
  } else {
    try {
      expected = [...new Set(expectedPaths.map(normalizeExpectedPath))]
    } catch (error) {
      violations.push(`expected Lighthouse route inventory is invalid: ${error.message}`)
    }
  }

  try {
    robotsRules = parseRobotsDisallows(robotsText)
  } catch (error) {
    violations.push(`robots.txt policy is invalid: ${error.message}`)
  }

  for (const prefix of LHCI_PROTECTED_ROUTE_PREFIXES) {
    if (!robotsDisallowsPath(prefix, robotsRules)) {
      violations.push(`robots.txt does not disallow configured protected prefix ${prefix}`)
    }
  }

  if (!Array.isArray(reports) || reports.length === 0) {
    violations.push("no Lighthouse LHR reports were provided")
    return { results, violations }
  }

  if (expectedRuns !== undefined) {
    if (!Number.isInteger(expectedRuns) || expectedRuns < 1) {
      violations.push("expected Lighthouse run count is invalid")
    } else if (expected.length > 0) {
      const reportCounts = new Map(expected.map((pathname) => [pathname, 0]))
      for (const report of reports) {
        try {
          const parsed = parseReportUrl(report)
          const route = parsed.requestedPath ?? parsed.pathname
          if (reportCounts.has(route)) reportCounts.set(route, reportCounts.get(route) + 1)
        } catch {
          // The route-policy loop below reports malformed URLs with the
          // detailed, redacted diagnostic. Completeness only counts valid
          // reports and therefore deliberately does not duplicate that error.
        }
      }
      for (const [pathname, count] of reportCounts) {
        if (count !== expectedRuns) {
          violations.push(
            `expected Lighthouse route ${pathname} has ${count} report(s); expected ${expectedRuns}`
          )
        }
      }
    }
  }

  reports.forEach((report, index) => {
    const label = reportLabel(report, index)
    let route
    try {
      route = parseReportUrl(report)
    } catch (error) {
      violations.push(`${label}: ${error.message}`)
      return
    }

    const { pathname, requestedPath, parsed } = route
    const classification = classifyLhciPath(pathname)
    const crawlAudit = getCrawlAudit(report)
    const crawlScore = finiteScore(crawlAudit?.score)
    const seoScore = finiteScore(report?.categories?.seo?.score)
    const result = {
      classification,
      crawlScore,
      pathname,
      requestedPath,
      seoScore,
      url: report.finalUrl,
    }

    if (classification === "unknown") {
      violations.push(`${label}: ungoverned Lighthouse route ${pathname}`)
      results.push(result)
      return
    }

    if (classification === "not-found") {
      const statusAudit = report?.audits?.["http-status-code"]
      const statusScore = finiteScore(statusAudit?.score)
      if (crawlScore !== 0) {
        violations.push(`${label}: not-found route ${pathname} must not be crawlable (score 0)`)
      }
      if (statusScore !== 0 || statusAudit?.displayValue !== "404") {
        violations.push(`${label}: not-found route ${pathname} must preserve HTTP 404 status`)
      }
      results.push(result)
      return
    }

    if (!crawlAudit || crawlScore === null) {
      violations.push(`${label}: is-crawlable audit is missing or has no finite score`)
    }

    if (classification === "public") {
      if (seoScore === null || seoScore < LHCI_PUBLIC_SEO_MIN_SCORE) {
        violations.push(
          `${label}: public route ${pathname} SEO score ${seoScore ?? "missing"} is below ${LHCI_PUBLIC_SEO_MIN_SCORE}`
        )
      }
      if (crawlScore !== 1) {
        violations.push(`${label}: public route ${pathname} must be crawlable (score 1)`)
      }
    } else {
      if (crawlScore !== 0) {
        violations.push(`${label}: protected route ${pathname} must be blocked (score 0)`)
      }
      if (!robotsDisallowsPath(pathname, robotsRules)) {
        violations.push(`${label}: robots.txt does not disallow protected route ${pathname}`)
      }
      if (!hasRobotsSource(crawlAudit, parsed.href)) {
        violations.push(`${label}: protected route ${pathname} is not blocked by robots.txt`)
      }
    }

    results.push(result)
  })

  if (expected.length > 0) {
    const observed = new Set()
    for (const result of results) {
      observed.add(result.pathname)
      if (result.requestedPath) observed.add(result.requestedPath)
    }
    for (const expectedPath of expected) {
      if (!observed.has(expectedPath)) {
        violations.push(`expected Lighthouse route ${expectedPath} has no report`)
      }
    }
  }

  return { results, violations }
}

async function readLighthouseReports(reportsDir) {
  let entries
  try {
    entries = await readdir(reportsDir, { withFileTypes: true })
  } catch (error) {
    throw new Error(`Unable to read Lighthouse report directory ${reportsDir}: ${error.message}`)
  }

  const reportFiles = entries
    .filter((entry) => entry.isFile() && REPORT_FILE_PATTERN.test(entry.name))
    .map((entry) => entry.name)
    .sort()

  if (reportFiles.length === 0) {
    throw new Error(`No Lighthouse LHR reports found in ${reportsDir}`)
  }

  return Promise.all(
    reportFiles.map(async (fileName) => {
      const reportPath = path.join(reportsDir, fileName)
      let parsed
      try {
        parsed = JSON.parse(await readFile(reportPath, "utf8"))
      } catch (error) {
        throw new Error(`Unable to parse Lighthouse report ${reportPath}: ${error.message}`)
      }
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error(`Lighthouse report ${reportPath} is not a JSON object`)
      }
      return { ...parsed, __lhciReportPath: reportPath }
    })
  )
}

export async function assertLhciRoutePolicy({
  reportsDir = path.join(MODULE_ROOT, ".lighthouseci"),
  robotsPath = path.join(MODULE_ROOT, "public", "robots.txt"),
  robotsText: providedRobotsText,
  expectedPaths = LHCI_DEFAULT_EXPECTED_PATHS,
  expectedRuns,
} = {}) {
  let robotsText = providedRobotsText
  if (robotsText === undefined) {
    try {
      robotsText = await readFile(robotsPath, "utf8")
    } catch (error) {
      throw new Error(`Unable to read canonical robots.txt ${robotsPath}: ${error.message}`)
    }
  }

  const reports = await readLighthouseReports(reportsDir)
  const outcome = evaluateLhciRoutePolicy(reports, {
    robotsText,
    expectedPaths,
    expectedRuns,
  })
  if (outcome.violations.length > 0) {
    throw new Error(
      `Lighthouse route policy failed with ${outcome.violations.length} violation(s):\n` +
        outcome.violations.map((violation) => `- ${violation}`).join("\n")
    )
  }

  console.log(`Lighthouse route policy passed for ${outcome.results.length} report(s).`)
  return outcome
}

const isMainModule =
  process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)

if (isMainModule) {
  assertLhciRoutePolicy().catch((error) => {
    console.error(error)
    process.exitCode = 1
  })
}
