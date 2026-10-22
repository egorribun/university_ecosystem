import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

const specUrl = new URL("./messenger-keyboard-focus.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const modalUrl = new URL("../../src/components/messenger/NewChatModal.tsx", import.meta.url)
const sidebarUrl = new URL("../../src/components/messenger/MessengerSidebar.tsx", import.meta.url)
const focusTrapUrl = new URL("../../src/hooks/useFocusTrap.ts", import.meta.url)
const appShellUrl = new URL("../../src/contexts/AppShellContext.tsx", import.meta.url)

test("live Messenger Escape flow closes its dialog and restores the trigger focus", async () => {
  let spec
  try {
    spec = await readFile(specUrl, "utf8")
  } catch {
    assert.fail("the executable live Messenger keyboard/focus scenario must exist")
  }

  const [config, modal, sidebar, focusTrap, appShell] = await Promise.all([
    readFile(configUrl, "utf8"),
    readFile(modalUrl, "utf8"),
    readFile(sidebarUrl, "utf8"),
    readFile(focusTrapUrl, "utf8"),
    readFile(appShellUrl, "utf8"),
  ])

  assert.match(config, /testDir:\s*["']\.\/tests\/e2e-live["']/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
  assert.match(modal, /role=["']dialog["']/u)
  assert.match(modal, /aria-modal=["']true["']/u)
  assert.match(modal, /useFocusTrap<.*>\(\s*\{\s*active:\s*open[\s\S]*?returnFocus:\s*true/u)
  assert.match(modal, /event\.key === ["']Escape["']/u)
  assert.match(
    modal,
    /setOverlayState\(overlayStateId,\s*\{\s*blurred:\s*false,\s*scrollLocked:\s*true\s*\}\)/u
  )
  assert.match(modal, /return\s*\(\)\s*=>\s*setOverlayState\(overlayStateId,\s*null\)/u)
  assert.match(sidebar, /id=["']messenger-new-chat-btn["']/u)
  assert.match(sidebar, /aria-label=\{t\(["']messenger:newChat["']\)\}/u)
  assert.match(focusTrap, /returnFocusOnDeactivate:\s*returnFocus/u)
  assert.match(appShell, /document\.body\.style\.overflow = ["']hidden["']/u)
  assert.match(appShell, /document\.body\.style\.overflow = previousOverflowRef\.current/u)

  assert.match(
    spec,
    /Escape closes the new-chat dialog and restores keyboard focus to its trigger/u
  )
  assert.match(spec, /import \{ randomUUID \} from ["']node:crypto["']/u)
  assert.match(spec, /const identity = randomUUID\(\)/u)
  assert.match(spec, /freshPassword\(\)/u)
  assert.match(spec, /await loginAs\(adminPage,\s*["']admin["']\)/u)
  assert.match(spec, /await page\.goto\(["']\/register["']\)/u)
  assert.match(spec, /registrationAttempted = true/u)
  assert.match(spec, /loginWith\(page, email, password\)/u)
  assert.match(spec, /getByRole\(["']button["'],\s*\{\s*name:\s*["']Новый чат["']/u)
  assert.match(spec, /getByRole\(["']dialog["']\)/u)
  assert.match(spec, /page\.keyboard\.press\(["']Escape["']\)/u)
  assert.match(spec, /expect\(dialog\)\.toHaveCount\(0\)/u)
  assert.match(spec, /expect\(newChatTrigger\)\.toBeFocused\(\)/u)
  assert.match(spec, /overflowBeforeDialog/u)
  assert.match(spec, /\.toBe\(["']hidden["']\)/u)
  assert.match(spec, /\.toBe\(overflowBeforeDialog\)/u)
  assert.match(spec, /entry\.email === email && entry\.full_name === fullName/u)
  assert.ok(
    spec.includes("fetch(`/api/v1/users/${encodeURIComponent(userId)}`"),
    "cleanup must delete only the exact generated account id"
  )
  assert.match(spec, /headers:\s*\{\s*["']X-CSRF-Token["']:\s*csrfToken\s*\}/u)
  assert.doesNotMatch(
    spec,
    /\b(?:routeWebSocket|server\.use|vi\.mock|page\.route)\b/u,
    "the Escape and scroll-lock acceptance must use the real UI and API"
  )
})

test("live NewChat search lets keyboard users traverse real user results without selection", async () => {
  const [spec, modal] = await Promise.all([readFile(specUrl, "utf8"), readFile(modalUrl, "utf8")])

  assert.match(spec, /ArrowDown and ArrowUp navigate search results without opening a chat/u)
  assert.match(spec, /search\.fill\(["']Synthetic Demo["']\)/u)
  assert.match(spec, /getByRole\(["']listbox["']/u)
  assert.match(spec, /getByRole\(["']option["']\)/u)
  assert.match(spec, /page\.keyboard\.press\(["']ArrowDown["']\)/u)
  assert.match(spec, /page\.keyboard\.press\(["']ArrowUp["']\)/u)
  assert.match(spec, /expect\(firstOption\)\.toBeFocused\(\)/u)
  assert.match(spec, /expect\(search\)\.toBeFocused\(\)/u)
  assert.match(spec, /expect\(dialog\)\.toBeVisible\(\)/u)
  assert.match(
    spec,
    /expect\(firstOption\)\.toHaveAttribute\(["']aria-selected["'],\s*["']false["']\)/u
  )
  assert.doesNotMatch(spec, /page\.keyboard\.press\(["']Enter["']\)/u)

  assert.match(modal, /const userListRef = useRef<HTMLDivElement \| null>\(null\)/u)
  assert.match(modal, /const handleUserSearchKeyDown/u)
  assert.match(modal, /const handleUserOptionKeyDown/u)
  assert.match(modal, /event\.key === ["']ArrowDown["']/u)
  assert.match(modal, /event\.key === ["']ArrowUp["']/u)
  assert.match(modal, /onKeyDown=\{handleUserSearchKeyDown\}/u)
  assert.match(modal, /onKeyDown=\{handleUserOptionKeyDown\}/u)
})
