import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

const specUrl = new URL("./push-permission-denied.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const sectionUrl = new URL(
  "../../src/pages/settings/sections/NotificationsSection.tsx",
  import.meta.url
)
const ruNotificationsUrl = new URL("../../src/i18n/locales/ru/notifications.json", import.meta.url)
const enNotificationsUrl = new URL("../../src/i18n/locales/en/notifications.json", import.meta.url)
const ruSettingsUrl = new URL("../../src/i18n/locales/ru/settings.json", import.meta.url)
const enSettingsUrl = new URL("../../src/i18n/locales/en/settings.json", import.meta.url)

test("live Chromium keeps a denied notification permission read-only across reload", async () => {
  let spec
  try {
    spec = await readFile(specUrl, "utf8")
  } catch {
    assert.fail("the denied-permission live browser scenario must exist")
  }

  const [
    config,
    section,
    ruNotificationsText,
    enNotificationsText,
    ruSettingsText,
    enSettingsText,
  ] = await Promise.all([
    readFile(configUrl, "utf8"),
    readFile(sectionUrl, "utf8"),
    readFile(ruNotificationsUrl, "utf8"),
    readFile(enNotificationsUrl, "utf8"),
    readFile(ruSettingsUrl, "utf8"),
    readFile(enSettingsUrl, "utf8"),
  ])
  const ruNotifications = JSON.parse(ruNotificationsText)
  const enNotifications = JSON.parse(enNotificationsText)
  const ruSettings = JSON.parse(ruSettingsText)
  const enSettings = JSON.parse(enSettingsText)

  assert.match(
    spec,
    /Chromium shows the denied notification permission without creating a subscription/u
  )
  assert.match(spec, /browserName !== "chromium"/u)
  assert.match(spec, /newBrowserCDPSession\(\)/u)
  assert.match(spec, /Target\.getBrowserContexts/u)
  assert.match(spec, /Browser\.setPermission/u)
  assert.match(spec, /browserContextId/u)
  assert.match(spec, /permission:\s*\{\s*name:\s*["']notifications["']\s*\}/u)
  assert.match(spec, /setting:\s*["']denied["']/u)
  assert.match(spec, /await loginAs\(page,\s*["']student["']\)/u)
  assert.match(spec, /await page\.goto\(["']\/settings\?tab=3["']\)/u)
  assert.match(spec, /await expectDeniedSettings\(page\)/u)
  assert.match(spec, /await page\.reload\(\)[\s\S]*?await expectDeniedSettings\(page\)/u)
  assert.match(spec, /Notification\.permission/u)
  assert.match(spec, /navigator\.serviceWorker\.ready/u)
  assert.match(spec, /registration\.pushManager\.getSubscription\(\)/u)
  assert.match(spec, /getByRole\(["']switch[\s\S]*?toHaveCount\(0\)/u)
  assert.match(spec, /subscriptionRequests[\s\S]*?toBe\(0\)/u)
  assert.doesNotMatch(spec, /grantPermissions|pushSwitch\.click\(\)|requestPermission\(\)/u)
  assert.doesNotMatch(
    spec,
    /page\.route|routeFromHAR|routeWebSocket|PushManager\.prototype|Notification\s*=/iu
  )
  assert.doesNotMatch(spec, /page\.request\.(?:post|put|patch|delete)/u)

  assert.match(section, /permissionDenied\s*=\s*notificationPermission\s*===\s*["']denied["']/u)
  assert.match(section, /permissionDenied\s*\?\s*\([\s\S]*?settings:notifications\.status/u)
  assert.match(section, /settings:notifications\.toggles\.notifications\.aria/u)
  assert.equal(ruNotifications.permission.denied, "запрещено")
  assert.equal(enNotifications.permission.denied, "blocked")
  assert.match(ruSettings.notifications.status, /\{\{status\}\}/u)
  assert.match(enSettings.notifications.status, /\{\{status\}\}/u)
  assert.match(spec, /Текущее состояние:\\s\*запрещено|Current status:\\s\*blocked/u)

  assert.match(config, /testDir:\s*["']\.\/tests\/e2e-live["']/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
  assert.match(config, /name:\s*["']desktop["']/u)
  assert.match(config, /name:\s*["']mobile["']/u)
  assert.match(config, /trace:\s*["']off["']/u)
  assert.match(config, /screenshot:\s*["']off["']/u)
  assert.match(config, /video:\s*["']off["']/u)
})
