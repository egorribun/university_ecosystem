import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import { URL } from "node:url"

const specUrl = new URL("./messenger-a11y.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const frontendAgentsUrl = new URL("../../AGENTS.md", import.meta.url)
const modalUrl = new URL("../../src/components/messenger/NewChatModal.tsx", import.meta.url)
const focusTrapUrl = new URL("../../src/hooks/useFocusTrap.ts", import.meta.url)
const appShellUrl = new URL("../../src/contexts/AppShellContext.tsx", import.meta.url)

const [config, frontendAgents, modal, focusTrap, appShell] = await Promise.all([
  readFile(configUrl, "utf8"),
  readFile(frontendAgentsUrl, "utf8"),
  readFile(modalUrl, "utf8"),
  readFile(focusTrapUrl, "utf8"),
  readFile(appShellUrl, "utf8"),
])

test("Messenger accessibility live acceptance is discovered by desktop and mobile projects", async () => {
  let spec
  try {
    spec = await readFile(specUrl, "utf8")
  } catch {
    assert.fail("the combined live Messenger accessibility scenario must exist")
  }

  assert.match(config, /testDir:\s*["']\.\/tests\/e2e-live["']/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
  assert.match(config, /name:\s*["']desktop["']/u)
  assert.match(config, /name:\s*["']mobile["']/u)
  assert.match(spec, /testInfo\.project\.name\s*===\s*["']mobile["']/u)
  assert.match(spec, /width:\s*360/u)
  assert.match(spec, /width:\s*1440/u)
  assert.match(spec, /await loginAs\(page,\s*["']student["']\)/u)
  assert.match(spec, /await page\.goto\(["']\/messenger["']\)/u)
})

test("the real dialog traps focus, supports arrow-key search, and restores focus and scroll", async () => {
  const spec = await readFile(specUrl, "utf8")

  assert.match(modal, /role=["']dialog["']/u)
  assert.match(modal, /aria-modal=["']true["']/u)
  assert.match(modal, /aria-labelledby=\{titleId\}/u)
  assert.match(modal, /aria-describedby=\{descriptionId\}/u)
  assert.match(modal, /useFocusTrap<.*>\(\s*\{\s*active:\s*open/u)
  assert.match(modal, /returnFocus:\s*true/u)
  assert.match(focusTrap, /returnFocusOnDeactivate:\s*returnFocus/u)
  assert.match(modal, /event\.key === ["']Escape["']/u)
  assert.match(modal, /event\.key === ["']ArrowDown["']/u)
  assert.match(modal, /event\.key === ["']ArrowUp["']/u)
  assert.match(appShell, /document\.body\.style\.overflow = ["']hidden["']/u)
  assert.match(appShell, /document\.body\.style\.overflow = previousOverflowRef\.current/u)

  assert.match(spec, /Messenger dialog supports keyboard access/u)
  assert.match(spec, /page\.keyboard\.press\(["']Tab["']\)/u)
  assert.match(spec, /page\.keyboard\.press\(["']Shift\+Tab["']\)/u)
  assert.match(spec, /expect\(close\)\.toBeFocused\(\)/u)
  assert.match(spec, /expect\(search\)\.toBeFocused\(\)/u)
  assert.match(spec, /page\.keyboard\.press\(["']ArrowDown["']\)/u)
  assert.match(spec, /page\.keyboard\.press\(["']ArrowUp["']\)/u)
  assert.match(spec, /expect\(firstOption\)\.toBeFocused\(\)/u)
  assert.match(
    spec,
    /expect\(firstOption\)\.toHaveAttribute\(["']aria-selected["'],\s*["']false["']\)/u
  )
  assert.match(spec, /page\.keyboard\.press\(["']Escape["']\)/u)
  assert.match(spec, /expect\(newChatTrigger\)\.toBeFocused\(\)/u)
  assert.match(spec, /overflowBeforeDialog/u)
  assert.match(spec, /\.toBe\(["']hidden["']\)/u)
  assert.match(spec, /\.toBe\(overflowBeforeDialog\)/u)
})

test("hit-target audit measures rendered browser geometry without creating a chat", async () => {
  const spec = await readFile(specUrl, "utf8")

  assert.match(frontendAgents, /Minimum touch target size of \*\*44x44px\*\*/u)
  assert.match(frontendAgents, /min-h-\[24px\] px-2 py-1\.5/u)
  assert.match(spec, /getBoundingClientRect\(\)/u)
  assert.match(spec, /window\.getComputedStyle\(element\)/u)
  assert.match(spec, /element\.getClientRects\(\)\.length === 0/u)
  assert.match(spec, /kind === "link" \? height < 24 : width < 44 \|\| height < 44/u)
  assert.match(spec, /undersizedTargets[\s\S]*?\.toEqual\(\[\]\)/u)
  assert.match(spec, /groupCreate[\s\S]*?toBeDisabled\(\)/u)
  assert.doesNotMatch(spec, /groupCreate\.click\(/u)
})

test("accessibility behavior is driven by the browser and seeded UI, without network mocks or writes", async () => {
  const spec = await readFile(specUrl, "utf8")

  assert.match(spec, /await page\.keyboard\.press/u)
  assert.match(spec, /await page\.emulateMedia\(\{ reducedMotion: ["']reduce["'] \}\)/u)
  assert.doesNotMatch(
    spec,
    /\b(?:vi\.mock|server\.use|page\.route|routeWebSocket|route\.fulfill)\b/u
  )
  assert.doesNotMatch(spec, /page\.request\.(?:post|put|patch|delete)\(/u)
  assert.doesNotMatch(spec, /await page\.goto\(["']\/register["']\)/u)
  assert.doesNotMatch(spec, /console\.(?:log|info|debug)\(/u)
})
