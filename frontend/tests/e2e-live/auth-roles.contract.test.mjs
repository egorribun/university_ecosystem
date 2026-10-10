import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import { URL } from "node:url"

const specUrl = new URL("./auth-roles.live.spec.ts", import.meta.url)
const fixtureUrl = new URL("./fixtures.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const packageUrl = new URL("../../package.json", import.meta.url)
const loginRouteUrl = new URL("../../src/routes/_public/login.tsx", import.meta.url)
const loginPageUrl = new URL("../../src/pages/Login.tsx", import.meta.url)
const loginFormUrl = new URL("../../src/components/auth/LoginCredentialForm.tsx", import.meta.url)
const loginFlowUrl = new URL("../../src/hooks/auth/useLoginFlow.ts", import.meta.url)
const russianAuthUrl = new URL("../../src/i18n/locales/ru/auth.json", import.meta.url)
const englishAuthUrl = new URL("../../src/i18n/locales/en/auth.json", import.meta.url)

test("seeded student, teacher, and admin sessions resolve to their own identity", async () => {
  const [spec, fixtures, config] = await Promise.all([
    readFile(specUrl, "utf8"),
    readFile(fixtureUrl, "utf8"),
    readFile(configUrl, "utf8"),
  ])

  assert.match(spec, /const ROLE_NAMES:\s*Role\[\]\s*=\s*\["student",\s*"teacher",\s*"admin"\]/u)
  assert.match(spec, /for\s*\(const role of ROLE_NAMES\)/u)
  assert.match(spec, /await loginAs\(page, role\)/u)
  assert.match(spec, /page\.request\.get\(["']\/api\/v1\/users\/me["']\)/u)
  assert.match(spec, /expect\(\(await me\.json\(\)\)\.email\)\.toBe\(ROLES\[role\]\.email\)/u)
  for (const role of ["student", "teacher", "admin"]) {
    assert.match(fixtures, new RegExp(`${role}:\\s*\\{`, "u"))
  }
  assert.match(config, /testDir:\s*["']\.\/tests\/e2e-live["']/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
  assert.doesNotMatch(spec, /page\.route\(|routeWebSocket|useMockApi/u)
})

test("role authentication uses the real login form and does not intercept auth traffic", async () => {
  const fixtures = await readFile(fixtureUrl, "utf8")
  const loginHelpersStart = fixtures.indexOf("export async function submitLogin")
  const loginHelpersEnd = fixtures.indexOf("export function freshPassword", loginHelpersStart)
  const loginHelpers =
    loginHelpersStart >= 0 && loginHelpersEnd > loginHelpersStart
      ? fixtures.slice(loginHelpersStart, loginHelpersEnd)
      : undefined

  assert.ok(loginHelpers, "login helper implementation is present in the shared fixture")
  assert.match(
    fixtures,
    /export async function submitLogin\(\s*page: Page,\s*email: string,\s*password: string,\s*cleanupDeadlineAtMs\?: number,\s*maximumOperationTimeoutMs = LIVE_OWNED_CLEANUP_OPERATION_TIMEOUT_MS\s*\): Promise<void> \{[\s\S]*?await page\.goto\(["']\/login["'],\s*operationOptions\(45_000\)\)/u
  )
  assert.match(
    loginHelpers,
    /getByRole\(["']textbox["'][\s\S]*?\.fill\(email,\s*operationOptions\(15_000\)\)/u
  )
  assert.match(
    loginHelpers,
    /getByLabel\(["']Пароль["'][\s\S]*?\.fill\(password,\s*operationOptions\(15_000\)\)/u
  )
  assert.match(
    loginHelpers,
    /getByRole\(["']button["'][\s\S]*?\.click\(operationOptions\(15_000\)\)/u
  )
  assert.match(
    loginHelpers,
    /export async function loginAs\(\s*page: Page,\s*role: Role,\s*cleanupDeadlineAtMs\?: number,\s*maximumOperationTimeoutMs = LIVE_OWNED_CLEANUP_OPERATION_TIMEOUT_MS\s*\): Promise<void> \{\s*await loginWith\(\s*page,\s*ROLES\[role\]\.email,\s*ROLES\[role\]\.password,\s*cleanupDeadlineAtMs,\s*maximumOperationTimeoutMs\s*\)/u
  )
  assert.doesNotMatch(loginHelpers, /page\.route\(|routeWebSocket|\.fulfill\(|useMockApi/u)
})

test("auth roles contract is part of the shared live-contract preflight", async () => {
  const packageJson = JSON.parse(await readFile(packageUrl, "utf8"))
  assert.match(
    packageJson.scripts?.["test:e2e:live:contract"] ?? "",
    /tests\/e2e-live\/auth-roles\.contract\.test\.mjs/u
  )
})

test("admin API probes report only bounded status diagnostics before UI navigation", async () => {
  const spec = await readFile(specUrl, "utf8")
  assert.match(spec, /import \{ reportLiveHttpStatus \} from "\.\/http-status-diagnostic"/u)
  for (const [check, response, destination] of [
    ["admin-users", "adminUsers", "/admin/users"],
    ["admin-feature-flags", "featureFlags", "/admin/feature-flags"],
  ]) {
    const report = `reportLiveHttpStatus(testInfo.project.name, "${check}", ${response}.status())`
    const reportIndex = spec.indexOf(report)
    const assertionIndex = spec.indexOf(`expect(${response}.status()`, reportIndex)
    const navigationIndex = spec.indexOf(`page.goto("${destination}")`, assertionIndex)
    assert.ok(reportIndex >= 0 && assertionIndex > reportIndex && navigationIndex > assertionIndex)
    assert.equal(spec.split(report).length - 1, 1)
  }
})

test("feature-flag UI diagnostics observe only the existing API response and release the listener", async () => {
  const spec = await readFile(specUrl, "utf8")
  const section = spec.slice(
    spec.indexOf('test("admin can access feature-flag diagnostics"'),
    spec.indexOf('for (const role of ["student", "teacher"]')
  )
  assert.match(
    section,
    /response\.request\(\)\.method\(\) === "GET"\s*&&\s*new URL\(response\.url\(\)\)\.pathname === "\/api\/v1\/admin\/feature-flags"/u
  )
  assert.match(
    section,
    /reportLiveHttpStatus\(testInfo\.project\.name, "admin-feature-flags-ui", response\.status\(\)\)/u
  )
  assert.match(
    section,
    /\.toBe\(200\)[\s\S]*?page\.on\("response", reportFeatureFlagsResponse\)\s*try \{[\s\S]*?page\.goto\("\/admin\/feature-flags"\)[\s\S]*?\.toBeVisible\(\)\s*\} finally \{\s*page\.off\("response", reportFeatureFlagsResponse\)/u
  )
  assert.equal([...section.matchAll(/page\.request\.get\(/gu)].length, 1)
  assert.doesNotMatch(
    section,
    /waitForResponse|response\.(?:body|json|text|headers)\(|console\.|process\.stdout/u
  )
})

test("real wrong-password acceptance checks localized generic feedback without echo", async () => {
  const [spec, loginRoute, loginPage, loginForm, loginFlow, russianSource, englishSource] =
    await Promise.all([
      readFile(specUrl, "utf8"),
      readFile(loginRouteUrl, "utf8"),
      readFile(loginPageUrl, "utf8"),
      readFile(loginFormUrl, "utf8"),
      readFile(loginFlowUrl, "utf8"),
      readFile(russianAuthUrl, "utf8"),
      readFile(englishAuthUrl, "utf8"),
    ])
  const russianAuth = JSON.parse(russianSource)
  const englishAuth = JSON.parse(englishSource)

  assert.equal(russianAuth.login.error, "Неверный email или пароль")
  assert.equal(englishAuth.login.error, "Incorrect email or password")
  assert.match(loginRoute, /createFileRoute\(["']\/_public\/login["']\)/u)
  assert.match(loginRoute, /lazy\(\(\) => import\(["']@\/pages\/Login["']\)\)/u)
  assert.match(loginRoute, /component:\s*Login/u)
  assert.match(loginPage, /<LoginCredentialForm\s+form=\{form\}\s*\/>/u)
  assert.match(loginFlow, /resolveAuthErrorMessage\(error,\s*t\(["']auth:login\.error["']\)\)/u)
  assert.match(loginForm, /id="email"/u)
  assert.match(loginForm, /id="password"/u)
  assert.match(loginForm, /id="login-submit"/u)

  const cases = spec.match(/const WRONG_PASSWORD_CASES = \[([\s\S]*?)\] as const/u)?.[1]
  assert.ok(cases, "wrong-password live cases are declared explicitly")
  const roleLocaleMessages = [
    ...cases.matchAll(
      /role:\s*["'](student|teacher|admin)["'],\s*language:\s*["'](ru|en)["'],\s*project:\s*["'](desktop|mobile)["'],\s*expectedError:\s*["']([^"']+)["']/gu
    ),
  ].map(([, role, language, project, message]) => [role, language, project, message])
  assert.deepEqual(roleLocaleMessages, [
    ["student", "ru", "desktop", russianAuth.login.error],
    ["teacher", "en", "mobile", englishAuth.login.error],
  ])
  const rejectedLoginStart = spec.indexOf('test.describe("localized rejected-login acceptance"')
  const adminSmokeStart = spec.indexOf('test("admin can access the admin page', rejectedLoginStart)
  assert.ok(rejectedLoginStart >= 0 && adminSmokeStart > rejectedLoginStart)
  const rejectedLoginSection = spec.slice(rejectedLoginStart, adminSmokeStart)
  assert.match(spec, /await page\.goto\(["']\/login["']\)/u)
  assert.match(spec, /window\.localStorage\.setItem\(["']ue:language["'],\s*selectedLanguage\)/u)
  assert.match(
    rejectedLoginSection,
    /context\.addCookies\(\[\{ name: "ue:language", value: language, url: liveBaseUrl \}\]\)[\s\S]*?page\.addInitScript\([\s\S]*?await page\.goto\("\/login"\)/u
  )
  assert.match(
    rejectedLoginSection,
    /page\.waitForFunction\(\(\) => window\.__APP_HYDRATED === true\)/u
  )
  assert.match(spec, /toHaveAttribute\(["']lang["'],\s*language\)/u)
  assert.match(rejectedLoginSection, /test\.describe\.configure\(\{\s*retries:\s*0\s*\}\)/u)
  assert.match(
    rejectedLoginSection,
    /test\.skip\(\s*testInfo\.project\.name\s*!==\s*project[\s\S]*?await page\.goto\(["']\/login["']\)/u
  )
  assert.match(rejectedLoginSection, /page\.locator\(["']#email["']\)\.fill\(identity\)/u)
  assert.match(rejectedLoginSection, /page\.locator\(["']#password["']\)\.fill\(wrongPassword\)/u)
  assert.match(
    rejectedLoginSection,
    /page\.waitForResponse\([\s\S]*?response\.request\(\)\.method\(\) === "POST"[\s\S]*?new URL\(response\.url\(\)\)\.pathname === "\/api\/v1\/auth\/login"/u
  )
  assert.match(rejectedLoginSection, /page\.locator\(["']#login-submit["']\)\.click\(\)/u)
  assert.match(
    rejectedLoginSection,
    /expect\(loginResponse\.status\(\), "rejected login must return HTTP 401"\)\.toBe\(401\)/u
  )
  assert.match(
    rejectedLoginSection,
    /page\s*\.locator\("form"\)\s*\.filter\(\{ has: page\.locator\("#login-submit"\) \}\)\s*\.getByRole\("alert"\)/u
  )
  assert.doesNotMatch(rejectedLoginSection, /page\.getByRole\("alert"\)|\.first\(\)/u)
  assert.match(
    rejectedLoginSection,
    /feedbackText\s*===\s*expectedError[\s\S]*?!feedbackText\.includes\(identity\)[\s\S]*?!feedbackText\.includes\(wrongPassword\)/u
  )
  assert.match(
    rejectedLoginSection,
    /visibleText\.includes\(identity\)[\s\S]*?visibleText\.includes\(wrongPassword\)/u
  )
  assert.match(rejectedLoginSection, /expect\(me\.status\(\)\)\.toBe\(401\)/u)
  assert.doesNotMatch(spec, /page\.route\(|routeWebSocket|useMockApi|\.fulfill\(/u)
})
