import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

const specUrl = new URL("./new-chat-hit-targets.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const modalUrl = new URL("../../src/components/messenger/NewChatModal.tsx", import.meta.url)
const frontendAgentsUrl = new URL("../../AGENTS.md", import.meta.url)

test("NewChat live target audit uses real seeded UI and checks computed hit areas", async () => {
  const [spec, config, modal, frontendAgents] = await Promise.all([
    readFile(specUrl, "utf8"),
    readFile(configUrl, "utf8"),
    readFile(modalUrl, "utf8"),
    readFile(frontendAgentsUrl, "utf8"),
  ])

  assert.match(config, /testDir:\s*["']\.\/tests\/e2e-live["']/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
  assert.match(spec, /await loginAs\(page,\s*["']teacher["']\)/u)
  assert.match(spec, /await page\.goto\(["']\/messenger["']\)/u)
  assert.match(spec, /testInfo\.project\.name\s*===\s*["']mobile["']/u)
  assert.match(spec, /width:\s*360/u)
  assert.match(spec, /width:\s*1440/u)
  assert.match(spec, /getByRole\(["']dialog["']\)/u)
  assert.match(spec, /getByRole\(["']tab["'],\s*\{\s*name:\s*["']Группа["']/u)
  assert.match(spec, /getByRole\(["']textbox["'],\s*\{\s*name:\s*["']Поиск пользователей["']/u)
  assert.match(spec, /getByRole\(["']option["']\)/u)
  assert.match(spec, /Удалить Иван Соколов/u)
  assert.match(spec, /getBoundingClientRect\(\)/u)
  assert.match(spec, /a\[href\].*role/u)
  assert.match(spec, /height\s*<\s*24/u)
  assert.match(spec, /width\s*<\s*44/u)
  assert.match(spec, /height\s*<\s*44/u)
  assert.match(spec, /groupCreate.*toBeDisabled\(\)/su)
  assert.doesNotMatch(spec, /groupCreate\.click\(/u)
  assert.doesNotMatch(spec, /page\.request\.(?:post|put|patch|delete)\(/u)
  assert.doesNotMatch(spec, /\b(?:vi\.mock|server\.use|page\.route|routeWebSocket)\b/u)

  assert.match(modal, /min-h-\[44px\].*min-w-\[44px\]/u)
  assert.match(modal, /role=["']tablist["']/u)
  assert.match(modal, /role=["']option["']/u)
  assert.match(modal, /min-h-\[60px\]/u)
  assert.match(frontendAgents, /Minimum touch target size of \*\*44x44px\*\*/u)
  assert.match(frontendAgents, /min-h-\[24px\] px-2 py-1\.5/u)

  // This dialog currently renders no text links. The live audit still includes
  // links in its selector so a future link is measured against the 24px rule.
  assert.doesNotMatch(modal, /<a\b|role=["']link["']/u)
  assert.match(spec, /button, input, textarea, select, a\[href\]/u)
  assert.match(spec, /\[role="link"\]/u)
})
