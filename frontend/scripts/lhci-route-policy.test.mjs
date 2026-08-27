import assert from "node:assert/strict"
import { mkdtemp, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import test from "node:test"

import routePolicyConfig from "./lhci-route-policy-config.cjs"
import {
  classifyLhciPath,
  assertLhciRoutePolicy,
  evaluateLhciRoutePolicy,
  parseRobotsDisallows,
  robotsDisallowsPath,
} from "./lhci-route-policy.mjs"

const ROBOTS = `User-agent: *
Disallow: /api/
Disallow: /news
Disallow: /admin/
Disallow: /dashboard
Disallow: /events
Disallow: /activity
Disallow: /map
Disallow: /messenger
Disallow: /profile
Disallow: /schedule
Disallow: /settings
`

function report(pathname, { seo = 1, crawl = 1, source = "/robots.txt" } = {}) {
  const finalUrl = `https://example.test${pathname}`
  return {
    finalUrl,
    requestedUrl: finalUrl,
    categories: { seo: { score: seo } },
    audits: {
      "is-crawlable": {
        score: crawl,
        details: {
          items: source ? [{ source: { url: `https://example.test${source}` } }] : [],
        },
      },
    },
  }
}

test("route classification is explicit and prefix-aware", () => {
  assert.equal(classifyLhciPath("/"), "public")
  assert.equal(classifyLhciPath("/news/"), "protected")
  assert.equal(classifyLhciPath("/news/42"), "protected")
  assert.equal(classifyLhciPath("/reset-password/token"), "public")
  assert.equal(classifyLhciPath("/dashboard/"), "protected")
  assert.equal(classifyLhciPath("/admin/settings"), "protected")
  assert.equal(classifyLhciPath("/dashboarding"), "unknown")
})

test("the LHCI matrix URL pattern covers query strings without matching lookalike routes", () => {
  const pattern = new RegExp(routePolicyConfig.publicSeoUrlPattern)
  assert.equal(pattern.test("https://example.test/login?next=%2Fdashboard"), true)
  assert.equal(pattern.test("https://example.test/reset-password/token#form"), true)
  assert.equal(pattern.test("https://example.test/newsletter"), false)
})

test("robots parser uses wildcard group and normalizes trailing slashes", () => {
  const rules = parseRobotsDisallows("User-agent: Googlebot\nDisallow: /dashboard\n\n" + ROBOTS)

  assert.equal(robotsDisallowsPath("/dashboard", rules), true)
  assert.equal(robotsDisallowsPath("/dashboard/metrics", rules), true)
  assert.equal(robotsDisallowsPath("/dashboarding", rules), false)
  assert.equal(robotsDisallowsPath("/admin", rules), true)
})

test("robots parser does not merge a wildcard group after Allow-only directives", () => {
  const rules = parseRobotsDisallows(`User-agent: *
Allow: /
User-agent: EvilBot
Disallow: /admin
`)

  assert.equal(robotsDisallowsPath("/admin", rules), false)
})

test("robots parser keeps malformed lines from crossing user-agent groups", () => {
  const rules = parseRobotsDisallows(`User-agent: *
foo
User-agent: EvilBot
Disallow: /settings
`)

  assert.equal(robotsDisallowsPath("/settings", rules), false)
})

test("public routes require SEO floor and crawlability", () => {
  const outcome = evaluateLhciRoutePolicy([report("/login")], {
    robotsText: ROBOTS,
    expectedPaths: ["/login"],
  })
  assert.deepEqual(outcome.violations, [])

  const lowSeo = evaluateLhciRoutePolicy([report("/login", { seo: 0.89 })], {
    robotsText: ROBOTS,
    expectedPaths: ["/login"],
  })
  assert.equal(lowSeo.violations.length, 1)
  assert.match(lowSeo.violations[0], /SEO score 0\.89/u)

  const blocked = evaluateLhciRoutePolicy([report("/login", { crawl: 0 })], {
    robotsText: ROBOTS,
    expectedPaths: ["/login"],
  })
  assert.equal(blocked.violations.length, 1)
  assert.match(blocked.violations[0], /must be crawlable/u)
})

test("protected routes require a robots.txt block and source attribution", () => {
  const outcome = evaluateLhciRoutePolicy([report("/dashboard/", { crawl: 0 })], {
    robotsText: ROBOTS,
    expectedPaths: ["/dashboard"],
  })
  assert.deepEqual(outcome.violations, [])

  const crawlable = evaluateLhciRoutePolicy([report("/dashboard", { crawl: 1 })], {
    robotsText: ROBOTS,
    expectedPaths: ["/dashboard"],
  })
  assert.equal(crawlable.violations.length, 1)
  assert.match(crawlable.violations.join("\n"), /must be blocked/u)

  const metaBlocked = evaluateLhciRoutePolicy(
    [report("/dashboard", { crawl: 0, source: "/index.html" })],
    { robotsText: ROBOTS, expectedPaths: ["/dashboard"] }
  )
  assert.equal(metaBlocked.violations.length, 1)
  assert.match(metaBlocked.violations[0], /not blocked by robots\.txt/u)

  const foreignRobots = evaluateLhciRoutePolicy(
    [
      {
        ...report("/dashboard", { crawl: 0 }),
        audits: {
          "is-crawlable": {
            score: 0,
            details: { items: [{ source: { url: "https://attacker.test/robots.txt" } }] },
          },
        },
      },
    ],
    { robotsText: ROBOTS, expectedPaths: ["/dashboard"] }
  )
  assert.equal(foreignRobots.violations.length, 1)
  assert.match(foreignRobots.violations[0], /not blocked by robots\.txt/u)
})

test("unknown routes and invalid robots policy fail closed", () => {
  const unknown = evaluateLhciRoutePolicy([report("/unexpected")], {
    robotsText: ROBOTS,
    expectedPaths: ["/unexpected"],
  })
  assert.equal(unknown.violations.length, 1)
  assert.match(unknown.violations[0], /ungoverned Lighthouse route/u)

  const noWildcard = evaluateLhciRoutePolicy([report("/dashboard", { crawl: 0 })], {
    robotsText: "User-agent: Googlebot\nDisallow: /dashboard\n",
    expectedPaths: ["/dashboard"],
  })
  assert.ok(noWildcard.violations.length > 2)
  assert.match(noWildcard.violations[0], /no User-agent: \*/u)

  const missingPrefix = evaluateLhciRoutePolicy([report("/news")], {
    robotsText: "User-agent: *\nDisallow: /dashboard\n",
    expectedPaths: ["/news"],
  })
  assert.match(
    missingPrefix.violations.join("\n"),
    /does not disallow configured protected prefix \/events/u
  )
})

test("empty and malformed report input is represented as a violation", () => {
  const empty = evaluateLhciRoutePolicy([], { robotsText: ROBOTS })
  assert.ok(empty.violations.length > 1)
  assert.match(empty.violations.join("\n"), /no Lighthouse LHR/u)

  const malformed = evaluateLhciRoutePolicy([{ finalUrl: "not-a-url" }], {
    robotsText: ROBOTS,
    expectedPaths: ["/news"],
  })
  assert.ok(malformed.violations.length > 1)
  assert.match(malformed.violations.join("\n"), /absolute URL/u)

  const redacted = evaluateLhciRoutePolicy([{ finalUrl: "not-a-url?token=do-not-log" }], {
    robotsText: ROBOTS,
    expectedPaths: ["/news"],
  })
  assert.doesNotMatch(redacted.violations.join("\n"), /do-not-log/u)

  const missingAudit = evaluateLhciRoutePolicy(
    [{ finalUrl: "https://example.test/login", categories: { seo: { score: 1 } } }],
    { robotsText: ROBOTS, expectedPaths: ["/login"] }
  )
  assert.ok(missingAudit.violations.length > 1)
  assert.match(missingAudit.violations.join("\n"), /is-crawlable audit/u)
  assert.match(missingAudit.violations.join("\n"), /must be crawlable/u)
})

test("route inventory rejects partial collections and honors redirected requests", () => {
  const partial = evaluateLhciRoutePolicy([report("/news")], {
    robotsText: ROBOTS,
    expectedPaths: ["/news", "/events"],
  })
  assert.match(partial.violations.join("\n"), /expected Lighthouse route \/events/u)

  const redirected = {
    ...report("/dashboard", { crawl: 0 }),
    requestedUrl: "https://example.test/",
  }
  const complete = evaluateLhciRoutePolicy([redirected], {
    robotsText: ROBOTS,
    expectedPaths: ["/"],
  })
  assert.deepEqual(complete.violations, [])
})

test("the CLI reader rejects empty and malformed report directories", async () => {
  const robotsPath = new URL("../public/robots.txt", import.meta.url)
  const reportsDir = await mkdtemp(path.join(tmpdir(), "lhci-route-policy-test-"))
  try {
    await assert.rejects(
      assertLhciRoutePolicy({ reportsDir, robotsPath }),
      /No Lighthouse LHR reports found/u
    )

    await writeFile(path.join(reportsDir, "assertion-results.json"), "{}", "utf8")
    await assert.rejects(
      assertLhciRoutePolicy({ reportsDir, robotsPath }),
      /No Lighthouse LHR reports found/u
    )

    await writeFile(path.join(reportsDir, "lhr-0.json"), "{malformed", "utf8")
    await assert.rejects(
      assertLhciRoutePolicy({ reportsDir, robotsPath }),
      /Unable to parse Lighthouse report/u
    )
  } finally {
    await rm(reportsDir, { recursive: true, force: true })
  }
})
