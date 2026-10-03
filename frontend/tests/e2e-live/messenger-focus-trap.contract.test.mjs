import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

const specUrl = new URL("./messenger-focus-trap.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const modalUrl = new URL("../../src/components/messenger/NewChatModal.tsx", import.meta.url)
const focusTrapUrl = new URL("../../src/hooks/useFocusTrap.ts", import.meta.url)
const escapeSpecUrl = new URL("./messenger-keyboard-focus.live.spec.ts", import.meta.url)

test("read-only Messenger live scenario covers focus-trap boundaries separately from Escape", async () => {
  const [spec, config, modal, focusTrap, escapeSpec] = await Promise.all([
    readFile(specUrl, "utf8"),
    readFile(configUrl, "utf8"),
    readFile(modalUrl, "utf8"),
    readFile(focusTrapUrl, "utf8"),
    readFile(escapeSpecUrl, "utf8"),
  ])

  assert.match(config, /testDir:\s*["']\.\/tests\/e2e-live["']/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
  assert.match(modal, /role=["']dialog["']/u)
  assert.match(modal, /aria-modal=["']true["']/u)
  assert.match(modal, /useFocusTrap<.*>\(\s*\{\s*active:\s*open/u)
  assert.match(focusTrap, /createFocusTrap\(container/u)

  assert.match(spec, /Tab and Shift\+Tab keep focus inside the read-only new-chat dialog/u)
  assert.match(spec, /await loginAs\(page,\s*["']student["']\)/u)
  assert.match(spec, /await page\.goto\(["']\/messenger["']\)/u)
  assert.match(spec, /getByRole\(["']dialog["']\)/u)
  assert.match(spec, /getByRole\(["']textbox["'],\s*\{\s*name:\s*["']Поиск пользователей["']/u)
  assert.match(spec, /page\.keyboard\.press\(["']Tab["']\)/u)
  assert.match(spec, /page\.keyboard\.press\(["']Shift\+Tab["']\)/u)
  assert.match(spec, /expect\(close\)\.toBeFocused\(\)/u)
  assert.match(spec, /expect\(search\)\.toBeFocused\(\)/u)
  assert.doesNotMatch(
    spec,
    /Escape|randomUUID|freshPassword|loginWith|request\.(?:post|put|patch|delete)|\.fill\(/u
  )
  assert.doesNotMatch(
    spec,
    /\b(?:vi\.mock|server\.use|page\.route|routeWebSocket)\b/u,
    "the seeded-user focus scenario must use the real Messenger UI and backend"
  )

  assert.match(escapeSpec, /page\.keyboard\.press\(["']Escape["']\)/u)
  assert.match(escapeSpec, /expect\(newChatTrigger\)\.toBeFocused\(\)/u)
})
