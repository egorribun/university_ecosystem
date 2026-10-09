import assert from "node:assert/strict"
import { randomUUID } from "node:crypto"
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"

import {
  buildAdminCaptureBasename,
  captureAdminScreenshot,
  classifyAdminPageSnapshot,
  createAdminSmokeRunDirectory,
  createAdminSmokeSidecar,
  isAdminCaptureSuccessful,
  parseAdminVisualCaptureMatrix,
} from "./admin-visual-smoke.mjs"

function validAdminMatrixEnvironment(outputDir) {
  return {
    VISUAL_CAPTURE_MATRIX: "1",
    VISUAL_WIDTHS: "390,768,1440",
    VISUAL_LOCALES: "en,ru",
    VISUAL_THEMES: "light,dark",
    VISUAL_HEIGHT: "800",
    SOURCE_SHA: "c".repeat(40),
    ORIGIN: "http://localhost",
    OUT_DIR: outputDir,
    TEST_EMAIL: "synthetic-admin@example.test",
    TEST_PASSWORD: randomUUID(),
  }
}

test("admin visual matrix validates private destination, source, role inputs, and dimensions", async () => {
  const temporaryRoot = await mkdtemp(path.join(os.tmpdir(), "admin-visual-matrix-"))
  const checkoutRoot = path.join(temporaryRoot, "checkout")
  const privateOutput = path.join(temporaryRoot, "private-output")
  const credentialedOrigin = new URL("https://example.test/path")
  credentialedOrigin.username = randomUUID()
  credentialedOrigin.password = randomUUID()
  try {
    const config = parseAdminVisualCaptureMatrix(validAdminMatrixEnvironment(privateOutput), {
      checkoutRoot,
    })
    assert.deepEqual(config.widths, [390, 768, 1440])
    assert.deepEqual(config.locales, ["en", "ru"])
    assert.deepEqual(config.themes, ["light", "dark"])
    assert.equal(config.height, 800)
    assert.equal(config.sourceSha, "c".repeat(40))
    assert.equal(config.evidenceKind, "real-browser-no-route-mocks")
    assert.equal(config.outputDir, privateOutput)
    assert.equal(parseAdminVisualCaptureMatrix({ VISUAL_CAPTURE_MATRIX: "0" }), null)

    const rejected = [
      [path.join(checkoutRoot, ".screenshots"), {}, /outside the checkout/u],
      [privateOutput, { VISUAL_WIDTHS: "390,200" }, /320 through 2560/u],
      [privateOutput, { VISUAL_LOCALES: "en,fr" }, /supported, unique values/u],
      [privateOutput, { VISUAL_THEMES: "system" }, /supported, unique values/u],
      [privateOutput, { SOURCE_SHA: "bad" }, /40-character/u],
      [privateOutput, { GITHUB_OUTPUT: "C:\\runner\\output" }, /must not publish/u],
      [privateOutput, { TEST_EMAIL: "" }, /explicit synthetic admin TEST_EMAIL/u],
      [privateOutput, { ORIGIN: credentialedOrigin.toString() }, /clean HTTP\(S\) origin/u],
    ]
    for (const [outputDir, overrides, message] of rejected) {
      assert.throws(
        () =>
          parseAdminVisualCaptureMatrix(
            { ...validAdminMatrixEnvironment(outputDir), ...overrides },
            { checkoutRoot }
          ),
        message
      )
    }
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true })
  }
})

test("admin capture filenames preserve baseline names and isolate width variants", () => {
  assert.equal(buildAdminCaptureBasename("/admin/audit", "ru", "dark"), "admin_audit_ru_dark")
  assert.equal(
    buildAdminCaptureBasename("/admin/audit", "ru", "dark", { width: 390 }),
    "admin_audit_ru_dark_w390"
  )
})

test("admin smoke rejects a login redirect even when the response is successful", () => {
  const result = classifyAdminPageSnapshot({
    routePath: "/admin/audit",
    finalUrl: "http://localhost/login?redirect=%2Fadmin%2Faudit",
    hasMainLandmark: true,
    hasAdminTheme: false,
    locale: "en",
    documentLanguage: "en",
    headingText: "Sign in",
  })

  assert.equal(result.ready, false)
  assert.equal(result.routeMatches, false)
  assert.equal(result.hasExpectedHeading, false)
})

test("admin smoke accepts only the requested admin page and its expected heading", () => {
  const result = classifyAdminPageSnapshot({
    routePath: "/admin/audit",
    finalUrl: "http://localhost/admin/audit",
    hasMainLandmark: true,
    hasAdminTheme: true,
    locale: "en",
    documentLanguage: "en",
    headingText: "Secure Audit Logs",
  })

  assert.deepEqual(result, {
    ready: true,
    routeMatches: true,
    hasMainLandmark: true,
    hasAdminTheme: true,
    localeMatches: true,
    hasExpectedHeading: true,
  })
})

test("admin smoke recognizes the requested locale heading for each configured admin page", () => {
  const pages = [
    ["/admin/audit", "Secure Audit Logs", "Защищённый аудит"],
    ["/admin/feature-flags", "Feature Flag Diagnostics", "Диагностика флагов функций"],
    ["/admin/notifications", "Notification queue", "Очередь уведомлений"],
    ["/admin/stories", "Stories management", "Управление сторис"],
    ["/admin/users", "Users", "Пользователи"],
  ]

  for (const [routePath, englishHeading, russianHeading] of pages) {
    for (const [locale, headingText] of [
      ["en", englishHeading],
      ["ru", russianHeading],
    ]) {
      assert.equal(
        classifyAdminPageSnapshot({
          routePath,
          finalUrl: `http://localhost${routePath}`,
          hasMainLandmark: true,
          hasAdminTheme: true,
          locale,
          documentLanguage: locale,
          headingText,
        }).ready,
        true,
        `${routePath} should match its ${locale} page heading`
      )
    }
  }
})

test("admin smoke rejects a heading from the wrong locale and mismatched document language", () => {
  const snapshot = {
    routePath: "/admin/audit",
    finalUrl: "http://localhost/admin/audit",
    hasMainLandmark: true,
    hasAdminTheme: true,
    locale: "ru",
    documentLanguage: "en",
    headingText: "Secure Audit Logs",
  }

  const wrongHeading = classifyAdminPageSnapshot({ ...snapshot, documentLanguage: "ru" })
  assert.equal(wrongHeading.ready, false)
  assert.equal(wrongHeading.localeMatches, true)
  assert.equal(wrongHeading.hasExpectedHeading, false)

  const wrongDocumentLanguage = classifyAdminPageSnapshot({
    ...snapshot,
    headingText: "Защищённый аудит",
  })
  assert.equal(wrongDocumentLanguage.ready, false)
  assert.equal(wrongDocumentLanguage.localeMatches, false)
})

test("admin smoke requires both the main landmark and admin theme scope", () => {
  const route = "/admin/audit"
  const snapshot = {
    routePath: route,
    finalUrl: `http://localhost${route}`,
    headingText: "Secure Audit Logs",
    hasMainLandmark: true,
    hasAdminTheme: true,
    locale: "en",
    documentLanguage: "en",
  }

  assert.equal(classifyAdminPageSnapshot({ ...snapshot, hasMainLandmark: false }).ready, false)
  assert.equal(classifyAdminPageSnapshot({ ...snapshot, hasAdminTheme: false }).ready, false)
})

test("admin smoke rejects a different admin page at a valid admin URL", () => {
  const result = classifyAdminPageSnapshot({
    routePath: "/admin/audit",
    finalUrl: "http://localhost/admin/users",
    hasMainLandmark: true,
    hasAdminTheme: true,
    locale: "en",
    documentLanguage: "en",
    headingText: "Users",
  })

  assert.equal(result.ready, false)
  assert.equal(result.routeMatches, false)
  assert.equal(result.hasExpectedHeading, false)
})

test("admin smoke rejects the expected path on a different origin", () => {
  const result = classifyAdminPageSnapshot({
    routePath: "/admin/audit",
    finalUrl: "https://foreign.example/admin/audit",
    expectedOrigin: "http://localhost",
    hasMainLandmark: true,
    hasAdminTheme: true,
    locale: "en",
    documentLanguage: "en",
    headingText: "Secure Audit Logs",
  })

  assert.equal(result.ready, false)
  assert.equal(result.routeMatches, false)
})

test("admin smoke never captures a screenshot until the page identity checks pass", async () => {
  const screenshots = []
  const page = {
    async screenshot(options) {
      screenshots.push(options)
    },
  }
  const invalidPage = classifyAdminPageSnapshot({
    routePath: "/admin/audit",
    finalUrl: "http://localhost/login",
    hasMainLandmark: false,
    hasAdminTheme: false,
    locale: "en",
    documentLanguage: "en",
    headingText: "Sign in",
  })

  assert.equal(await captureAdminScreenshot(page, invalidPage, { path: "login.png" }), null)
  assert.deepEqual(screenshots, [])

  const validPage = classifyAdminPageSnapshot({
    routePath: "/admin/audit",
    finalUrl: "http://localhost/admin/audit",
    hasMainLandmark: true,
    hasAdminTheme: true,
    locale: "ru",
    documentLanguage: "ru",
    headingText: "Защищённый аудит",
  })

  assert.equal(
    await captureAdminScreenshot(page, validPage, { path: "admin-audit.png" }),
    "admin-audit.png"
  )
  assert.deepEqual(screenshots, [{ path: "admin-audit.png" }])
})

test("monitoring success requires bootstrap status, ready page, and an actual screenshot", () => {
  const passed = {
    locale: "en",
    bootstrapPath: "/dashboard",
    bootstrapHttpStatus: 200,
    adminRoleConfirmed: true,
    pageReadiness: { ready: true },
    screenshotPath: ".screenshots/admin-visual-smoke/run-123/audit_en_light.png",
    redirectedToLogin: false,
  }
  assert.equal(isAdminCaptureSuccessful(passed), true)
  assert.equal(isAdminCaptureSuccessful({ ...passed, pageReadiness: { ready: false } }), false)
  assert.equal(isAdminCaptureSuccessful({ ...passed, screenshotPath: null }), false)
  assert.equal(isAdminCaptureSuccessful({ ...passed, bootstrapHttpStatus: 500 }), false)
  assert.equal(isAdminCaptureSuccessful({ ...passed, adminRoleConfirmed: false }), false)
  assert.equal(isAdminCaptureSuccessful({ ...passed, bootstrapPath: "/login" }), false)
  assert.equal(
    isAdminCaptureSuccessful({ ...passed, pageReadiness: { ready: true, viewportMatches: false } }),
    false
  )
  assert.equal(
    isAdminCaptureSuccessful({ ...passed, pageReadiness: { ready: true, themeMatches: false } }),
    false
  )
})

test("admin matrix sidecar binds evidence kind, source, and actual viewport dimensions", () => {
  const report = createAdminSmokeSidecar({
    routePath: "/admin/audit",
    locale: "ru",
    theme: "dark",
    bootstrapPath: "/dashboard",
    bootstrapHttpStatus: 200,
    finalUrl: "http://localhost/admin/audit?private=1",
    documentLanguage: "ru",
    redirectedToLogin: false,
    adminRoleConfirmed: true,
    pageReadiness: {
      ready: true,
      routeMatches: true,
      localeMatches: true,
      themeMatches: true,
      viewportMatches: true,
    },
    screenshotPath: "admin_audit_ru_dark_w390.png",
    consoleErrorCount: 0,
    hydrationErrorCount: 0,
    networkRequestCount: 3,
    width: 390,
    height: 800,
    sourceSha: "d".repeat(40),
    captureMode: "admin-live-visual-matrix",
  })
  assert.deepEqual(report.viewport, { width: 390, height: 800 })
  assert.equal(report.sourceSha, "d".repeat(40))
  assert.equal(report.captureMode, "admin-live-visual-matrix")
  assert.equal(report.evidenceKind, "real-browser-no-route-mocks")
  assert.equal(report.screenshotPath, "admin_audit_ru_dark_w390.png")
  assert.doesNotMatch(JSON.stringify(report), /private=1|admin@university\.dev|"sub"|"jti"/u)
})

test("published sidecars contain sanitized evidence without identity or raw console data", () => {
  const report = createAdminSmokeSidecar({
    routePath: "/admin/audit",
    locale: "ru",
    theme: "dark",
    bootstrapPath: "/dashboard",
    bootstrapHttpStatus: 200,
    finalUrl: "http://localhost/admin/audit?email=admin%40university.dev",
    documentLanguage: "ru",
    redirectedToLogin: false,
    adminRoleConfirmed: true,
    pageReadiness: { ready: true, routeMatches: true, localeMatches: true },
    screenshotPath: ".screenshots/admin-visual-smoke/run-123/audit_ru_dark.png",
    consoleErrorCount: 1,
    hydrationErrorCount: 0,
    networkRequestCount: 4,
    navigationError: new Error("raw console detail admin@university.dev sub=secret jti=secret"),
    profile: { email: "admin@university.dev", role: "admin" },
    jwtPayload: { sub: "secret-subject", jti: "secret-token-id" },
    consoleMessages: [{ text: "raw console detail" }],
  })
  const serialized = JSON.stringify(report)

  assert.equal(report.bootstrapPath, "/dashboard")
  assert.equal(report.bootstrapHttpStatus, 200)
  assert.equal(report.finalPath, "/admin/audit")
  assert.equal(report.locale, "ru")
  assert.equal(report.documentLanguage, "ru")
  assert.equal(report.screenshotPath, "audit_ru_dark.png")
  assert.equal(report.navigationError, "navigation_failed")
  assert.doesNotMatch(
    serialized,
    /admin@university\.dev|secret-subject|secret-token-id|raw console detail|"sub"|"jti"/u
  )
})

test("each smoke run gets a fresh directory without touching prior output", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "admin-smoke-contract-"))
  try {
    const previousOutput = path.join(root, "legacy.png")
    await writeFile(previousOutput, "user-owned output")

    const firstRun = await createAdminSmokeRunDirectory(root)
    const secondRun = await createAdminSmokeRunDirectory(root)

    assert.notEqual(firstRun, secondRun)
    assert.match(path.basename(firstRun), /^run-/u)
    assert.match(path.basename(secondRun), /^run-/u)
    assert.equal(await readFile(previousOutput, "utf8"), "user-owned output")
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test("admin smoke workflow summarizes all locale/theme captures and uploads only the current run", async () => {
  const workflow = await readFile(
    new URL("../../.github/workflows/admin-smoke-monitoring.yml", import.meta.url),
    "utf8"
  )

  assert.match(workflow, /5 admin routes × 2 locales × 2 themes = 20 expected/u)
  assert.match(workflow, /Bootstrap \/dashboard HTTP/u)
  assert.match(workflow, /r\.pageReadiness\?\.ready\s*===\s*true/u)
  assert.match(workflow, /Boolean\(r\.screenshotPath\)/u)
  assert.match(workflow, /r\.bootstrapPath\s*!==\s*"\/dashboard"/u)
  assert.match(workflow, /r\.adminRoleConfirmed\s*===\s*true/u)
  assert.match(workflow, /steps\.smoke\.outputs\.artifact_dir/u)
  assert.match(workflow, /real browser-context login with the seeded admin/u)
  assert.match(workflow, /default[\s\S]*?feature branch is not an active scheduled workflow/u)
  assert.doesNotMatch(workflow, /path:\s*frontend\/\.screenshots\/admin-visual-smoke\s*$/mu)
  assert.doesNotMatch(workflow, /(?:Wave\s+\d+|W\d{3}|AUDIT_WAVE|PR #\d+|cherry-pick)/iu)
})

test("live smoke sets each supported locale before dashboard bootstrap and admin routes", async () => {
  const source = await readFile(new URL("./admin-visual-smoke.mjs", import.meta.url), "utf8")

  assert.match(source, /const LOCALES = \["en", "ru"\]/u)
  assert.match(source, /name: "ue:language"/u)
  assert.match(source, /localStorage\.setItem\("ue:language", language\)/u)
  assert.match(
    source,
    /for \(const locale of locales\)[\s\S]*?setSmokeLocale\(page, locale[\s\S]*?bootstrapAdminSession\(page, locale\)[\s\S]*?for \(const route of ADMIN_ROUTES\)[\s\S]*?for \(const theme of themes\)[\s\S]*?smokeAdminRoute\(\s*page,\s*route,\s*locale,\s*theme/u
  )
})

test("matrix preflight runs before network/browser work and matrix filenames avoid baseline collisions", async () => {
  const source = await readFile(new URL("./admin-visual-smoke.mjs", import.meta.url), "utf8")
  const mainSource = source.slice(source.indexOf("async function main()"))
  assert.ok(
    mainSource.indexOf("parseAdminVisualCaptureMatrix()") <
      mainSource.indexOf("checkJwksEndpoint()")
  )
  assert.ok(
    mainSource.indexOf("parseAdminVisualCaptureMatrix()") < mainSource.indexOf("chromium.launch")
  )
  assert.match(source, /if \(!captureMatrix\) await publishCurrentRunPath\(runDir\)/u)
  assert.match(source, /_w\$\{captureConfig\.width\}/u)
})

test("admin smoke rejects missing or blank TEST_PASSWORD and uses the supplied runtime value", async () => {
  const { getAdminSmokeCredentials } = await import("./admin-visual-smoke.mjs")
  assert.ok(
    typeof getAdminSmokeCredentials === "function",
    "admin smoke must expose its credential validation boundary for contract tests"
  )

  assert.throws(() => getAdminSmokeCredentials({}), /TEST_PASSWORD/)
  assert.throws(() => getAdminSmokeCredentials({ TEST_PASSWORD: " \t " }), /TEST_PASSWORD/)

  const crypto = await import("node:crypto")
  const runtimePassword = crypto.randomBytes(32).toString("base64url")
  const credentials = getAdminSmokeCredentials({
    TEST_PASSWORD: runtimePassword,
  })
  assert.ok(
    credentials.password === runtimePassword,
    "admin smoke must use only the supplied transient password"
  )
})

test("admin smoke clears the password before either login failure path", async () => {
  const source = await readFile(new URL("admin-visual-smoke.mjs", import.meta.url), "utf8")
  const loginCall = source.indexOf("loginResult = await performLogin(context, credentials)")
  const catchStart = source.indexOf("} catch (err) {", loginCall)
  const catchEnd = source.indexOf('\n  }\n  credentials.password = ""', catchStart)
  assert.ok(
    loginCall >= 0 && catchStart > loginCall && catchEnd > catchStart,
    "the admin login failure handler must remain identifiable"
  )

  const failureHandler = source.slice(catchStart, catchEnd)
  const statements = failureHandler
    .slice(failureHandler.indexOf("{") + 1)
    .split(/\r?\n/u)
    .map((line) => line.trim())
    .filter(Boolean)
  assert.equal(
    statements[0],
    'credentials.password = ""',
    "the credential must be cleared before handling login errors"
  )

  const clearIndex = failureHandler.indexOf('credentials.password = ""')
  for (const failureMarker of [
    "X RS256 ASSERTION FAILED",
    "X LOGIN FAILED",
    "process.exit(3)",
    "process.exit(1)",
  ]) {
    assert.ok(
      failureHandler.indexOf(failureMarker) > clearIndex,
      "the password must be cleared before login failure logging and exit"
    )
  }
})

test("admin smoke clears the password before JWKS failure logging and exit", async () => {
  const source = await readFile(new URL("admin-visual-smoke.mjs", import.meta.url), "utf8")
  const jwksCall = source.indexOf("jwks = await checkJwksEndpoint()")
  const catchStart = source.indexOf("} catch (err) {", jwksCall)
  const catchEnd = source.indexOf("\n\n  let browser", catchStart)
  assert.ok(
    jwksCall >= 0 && catchStart > jwksCall && catchEnd > catchStart,
    "the JWKS pre-check failure handler must remain identifiable"
  )

  const failureHandler = source.slice(catchStart, catchEnd)
  const statements = failureHandler
    .slice(failureHandler.indexOf("{") + 1)
    .split(/\r?\n/u)
    .map((line) => line.trim())
    .filter(Boolean)
  assert.equal(
    statements[0],
    'credentials.password = ""',
    "the credential must be cleared before JWKS errors are logged"
  )
  assert.ok(
    failureHandler.indexOf('credentials.password = ""') < failureHandler.indexOf("console.error"),
    "the password must be cleared before logging or process exit"
  )
})

test("admin smoke workflow masks a per-run password before exposing it only to seed and smoke env", async () => {
  const workflow = (
    await readFile(
      new URL("../../.github/workflows/admin-smoke-monitoring.yml", import.meta.url),
      "utf8"
    )
  ).replace(/\r\n/gu, "\n")
  const blockForId = (id) => {
    const marker = "        id: " + id + "\n"
    const markerIndex = workflow.indexOf(marker)
    if (markerIndex < 0) return ""
    const start = workflow.lastIndexOf("\n      - name:", markerIndex) + 1
    const next = workflow.indexOf("\n      - name:", markerIndex + marker.length)
    return workflow.slice(start, next < 0 ? undefined : next)
  }
  const blockForName = (name) => {
    const marker = "      - name: " + name + "\n"
    const start = workflow.indexOf(marker)
    if (start < 0) return ""
    const next = workflow.indexOf("\n      - name:", start + marker.length)
    return workflow.slice(start, next < 0 ? undefined : next)
  }

  const generationStep = blockForId("admin_smoke_password")
  assert.ok(generationStep, "workflow must generate an ephemeral smoke password")
  assert.ok(
    /secrets\.token_urlsafe\(32\)/.test(generationStep),
    "workflow must use cryptographic per-run randomness"
  )
  assert.match(
    generationStep,
    /token_urlsafe\(32\)\s*\+\s*["']!Aa0["']/u,
    "workflow passwords must include each class required by the password policy"
  )
  const maskIndex = generationStep.indexOf("::add-mask::")
  const outputIndex = generationStep.indexOf("GITHUB_OUTPUT")
  assert.ok(
    maskIndex >= 0 && outputIndex > maskIndex,
    "workflow must mask the value before writing the step output"
  )
  const passwordOutputLines = generationStep
    .split(/\r?\n/)
    .filter((line) => line.includes("$password"))
  assert.ok(
    passwordOutputLines.length === 2 &&
      passwordOutputLines[0].includes("::add-mask::") &&
      passwordOutputLines[1].includes("GITHUB_OUTPUT"),
    "generated value may only go to the mask command and transient step output"
  )

  const stepOutput = "$" + "{{ steps.admin_smoke_password.outputs.password }}"
  const demoSeedStep = blockForName("Seed demo data")
  const seedStep = blockForName("Seed demo admin user")
  const smokeStep = blockForName("Run admin smoke script")
  const artifactStep = blockForName("Upload smoke reports")
  assert.ok(
    seedStep.includes("TEST_PASSWORD: " + stepOutput),
    "the admin seeder must receive the masked password as an environment value"
  )
  assert.ok(
    demoSeedStep && !demoSeedStep.includes("TEST_PASSWORD"),
    "base demo seeding must not receive the admin password"
  )
  assert.ok(
    smokeStep.includes("TEST_PASSWORD: " + stepOutput),
    "the browser smoke must receive the same password as an environment value"
  )
  assert.ok(
    workflow.split(stepOutput).length - 1 === 2,
    "only the seed and smoke steps may receive the generated value"
  )
  const passwordEnvLines = workflow
    .split(/\r?\n/u)
    .filter((line) => /^\s*TEST_PASSWORD:/u.test(line))
  assert.ok(
    passwordEnvLines.length === 2 &&
      passwordEnvLines.every((line) =>
        /^\s*TEST_PASSWORD:\s*\$\{\{\s*steps\.admin_smoke_password\.outputs\.password\s*\}\}/u.test(
          line
        )
      ),
    "workflow must not store a password literal"
  )
  assert.ok(
    !/\s--(?:test-)?password(?:[=\s]|$)/i.test(workflow),
    "password must never be passed through command-line arguments"
  )
  assert.ok(
    artifactStep &&
      !artifactStep.includes("TEST_PASSWORD") &&
      !artifactStep.includes("admin_smoke_password"),
    "the generated value must not enter uploaded reports"
  )
})
