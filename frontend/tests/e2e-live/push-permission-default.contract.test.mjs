import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

const specUrl = new URL("./push-permission-default.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const sourceContractUrl = new URL("./push-opt-in.contract.test.mjs", import.meta.url)
const existingLiveUrl = new URL("./push-subscription.live.spec.ts", import.meta.url)

test("live Chromium leaves default notification permission untouched until opt-in", async () => {
  let spec
  try {
    spec = await readFile(specUrl, "utf8")
  } catch {
    assert.fail("the default-permission live browser scenario must exist")
  }

  const [config, sourceContract, existingLive] = await Promise.all([
    readFile(configUrl, "utf8"),
    readFile(sourceContractUrl, "utf8"),
    readFile(existingLiveUrl, "utf8"),
  ])

  assert.match(
    spec,
    /Chromium leaves notification permission at default when settings are only opened/u
  )
  assert.match(spec, /browserName !== "chromium"/u)
  assert.match(spec, /await loginAs\(page, "student"\)/u)
  assert.match(spec, /await page\.goto\(["']\/settings\?tab=3["']\)/u)
  assert.match(spec, /navigator\.serviceWorker\.ready/u)
  assert.match(spec, /registration\.pushManager\.getSubscription\(\)/u)
  assert.match(spec, /Notification\.permission/u)
  assert.match(spec, /expect\(beforeSettings\.permission,[\s\S]*?\.toBe\("default"\)/u)
  assert.match(spec, /expect\(afterSettings\.permission,[\s\S]*?\.toBe\("default"\)/u)
  assert.match(spec, /hasSubscription:\s*subscription !== null/u)
  assert.match(spec, /expect\(subscriptionRequests,[\s\S]*?\.toBe\(0\)/u)
  assert.doesNotMatch(spec, /grantPermissions|pushSwitch\.click\(\)/u)
  assert.doesNotMatch(spec, /page\.route|routeWebSocket|PushManager\.prototype|vi\.mock/u)
  assert.doesNotMatch(spec, /page\.request\.(?:post|put|patch|delete)/u)

  assert.match(
    sourceContract,
    /loading notification settings only reads the owned browser subscription/u
  )
  assert.match(
    sourceContract,
    /explicit notifications switch owns permission and subscription requests/u
  )
  assert.match(existingLive, /grantPermissions\(\["notifications"\]/u)
  assert.match(existingLive, /pushSwitch\.click\(\)/u)

  assert.match(config, /testDir: "\.\/tests\/e2e-live"/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
  assert.match(config, /name: "desktop"/u)
  assert.match(config, /name: "mobile"/u)
  assert.match(config, /trace: "off"/u)
  assert.match(config, /screenshot: "off"/u)
  assert.match(config, /video: "off"/u)
})
