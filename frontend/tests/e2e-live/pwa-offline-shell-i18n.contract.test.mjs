import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

const specUrl = new URL("./pwa-offline-shell-i18n.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const rootRouteUrl = new URL("../../src/routes/__root.tsx", import.meta.url)
const i18nConfigUrl = new URL("../../src/i18n/config.ts", import.meta.url)
const enAuthUrl = new URL("../../src/i18n/locales/en/auth.json", import.meta.url)
const ruAuthUrl = new URL("../../src/i18n/locales/ru/auth.json", import.meta.url)
const offlineShellUrl = new URL("./pwa-offline-shell.live.spec.ts", import.meta.url)

test("live offline shell keeps the selected RU and EN locale with the real precached app", async () => {
  const [spec, config, rootRoute, i18nConfig, enAuth, ruAuth, offlineShell] = await Promise.all([
    readFile(specUrl, "utf8"),
    readFile(configUrl, "utf8"),
    readFile(rootRouteUrl, "utf8"),
    readFile(i18nConfigUrl, "utf8"),
    readFile(enAuthUrl, "utf8"),
    readFile(ruAuthUrl, "utf8"),
    readFile(offlineShellUrl, "utf8"),
  ])

  assert.match(config, /name:\s*["']desktop["']/u)
  assert.match(config, /name:\s*["']mobile["']/u)
  assert.match(config, /trace:\s*["']off["']/u)
  assert.match(config, /screenshot:\s*["']off["']/u)
  assert.match(config, /video:\s*["']off["']/u)
  assert.match(rootRoute, /localStorage\.getItem\(["']ue:language["']\)/u)
  assert.match(rootRoute, /document\.cookie\.match/u)
  assert.match(i18nConfig, /import enAuth from ["']\.\/locales\/en\/auth\.json["']/u)
  assert.match(i18nConfig, /import ruAuth from ["']\.\/locales\/ru\/auth\.json["']/u)
  assert.match(enAuth, /"title": "Sign up"/u)
  assert.match(ruAuth, /"title": "Регистрация"/u)
  assert.match(i18nConfig, /initAsync:\s*false/u)

  assert.match(spec, /for \(const language of \["en", "ru"\] as const\)/u)
  assert.match(spec, /value:\s*language/u)
  assert.match(
    spec,
    /page\.addInitScript\(\(selectedLanguage:\s*Language\)[\s\S]*?localStorage\.setItem\(["']ue:language["'],\s*selectedLanguage\)[\s\S]*?,\s*language\)/u
  )
  assert.match(spec, /signIn: "Sign in"[\s\S]*?signUp: "Sign up"[\s\S]*?name: "Name"/u)
  assert.match(spec, /signIn: "Вход"[\s\S]*?signUp: "Регистрация"[\s\S]*?name: "Имя"/u)
  assert.match(spec, /navigator\.serviceWorker\.ready/u)
  assert.match(spec, /navigator\.serviceWorker\.controller/u)
  assert.match(spec, /context\.setOffline\(true\)/u)
  assert.match(spec, /page\.goto\(["']\/register["']/u)
  assert.match(spec, /data-render-mode/u)
  assert.match(spec, /toHaveAttribute\(["']lang["'],\s*language\)/u)
  assert.match(spec, /name:\s*copy\.signUp/u)
  assert.match(spec, /name:\s*copy\.name/u)
  assert.match(spec, /auth\|common\|system/u)
  assert.match(spec, /offlineAssetRequests\.every/u)
  assert.doesNotMatch(spec, /page\.route|routeWebSocket|useMockApi|page\.request|\.fill\(/u)

  assert.match(offlineShell, /Network\.setCacheDisabled/u)
  assert.match(offlineShell, /workbox-precache/u)
  assert.match(offlineShell, /offlineAssetRequests\.every/u)
  assert.match(
    offlineShell,
    /updates the active service worker online and serves the new precached bundle offline/u
  )
  assert.match(offlineShell, /oldBundleCacheKeys[\s\S]*?not\.toContain/u)
  assert.match(offlineShell, /newBundleCacheEntries[\s\S]*?hasBuildMarker/u)
})
