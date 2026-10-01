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
    loginHelpers,
    /export async function submitLogin\([\s\S]*?page\.goto\(["']\/login["']\)/u
  )
  assert.match(loginHelpers, /getByRole\(["']textbox["'][\s\S]*?\.fill\(email\)/u)
  assert.match(loginHelpers, /getByLabel\(["']Пароль["'][\s\S]*?\.fill\(password\)/u)
  assert.match(loginHelpers, /getByRole\(["']button["'][\s\S]*?\.click\(\)/u)
  assert.match(
    loginHelpers,
    /export async function loginAs\(page: Page, role: Role\)[\s\S]*?ROLES\[role\]\.email[\s\S]*?ROLES\[role\]\.password/u
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
  assert.match(spec, /document\.cookie\s*=\s*`ue:language=\$\{selectedLanguage\}/u)
  assert.match(spec, /toHaveAttribute\(["']lang["'],\s*language\)/u)
  assert.match(rejectedLoginSection, /test\.describe\.configure\(\{\s*retries:\s*0\s*\}\)/u)
  assert.match(
    rejectedLoginSection,
    /test\.skip\(\s*testInfo\.project\.name\s*!==\s*project[\s\S]*?await page\.goto\(["']\/login["']\)/u
  )
  assert.match(rejectedLoginSection, /page\.locator\(["']#email["']\)\.fill\(identity\)/u)
  assert.match(rejectedLoginSection, /page\.locator\(["']#password["']\)\.fill\(wrongPassword\)/u)
  assert.match(rejectedLoginSection, /page\.locator\(["']#login-submit["']\)\.click\(\)/u)
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
