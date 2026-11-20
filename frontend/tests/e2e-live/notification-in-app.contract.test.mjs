import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { URL } from "node:url"
import test from "node:test"

const specUrl = new URL("./notification-in-app.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const chatApiUrl = new URL("../../../app/api/chat.py", import.meta.url)
const chatNotificationsUrl = new URL(
  "../../../app/services/chat/notification_service.py",
  import.meta.url
)
const quietHoursUrl = new URL("../../../app/services/notifications/quiet_hours.py", import.meta.url)
const notificationsApiUrl = new URL("../../../app/api/notifications.py", import.meta.url)
const notificationsBellUrl = new URL(
  "../../src/components/feedback/NotificationsBell.tsx",
  import.meta.url
)

test("live in-app chat notification stays unique and read after reload", async () => {
  let spec
  try {
    spec = await readFile(specUrl, "utf8")
  } catch {
    assert.fail("the executable live in-app notification scenario must exist")
  }

  const [config, chatApi, chatNotifications, quietHours, notificationsApi, notificationsBell] =
    await Promise.all([
      readFile(configUrl, "utf8"),
      readFile(chatApiUrl, "utf8"),
      readFile(chatNotificationsUrl, "utf8"),
      readFile(quietHoursUrl, "utf8"),
      readFile(notificationsApiUrl, "utf8"),
      readFile(notificationsBellUrl, "utf8"),
    ])

  assert.match(config, /testDir:\s*["']\.\/tests\/e2e-live["']/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
  assert.match(chatApi, /router = APIRouter\(prefix=["']\/chats["']/u)
  assert.match(chatApi, /@router\.post\(\s*["']\/\{chat_id\}\/messages["']/u)
  assert.match(chatNotifications, /generic_key = f["']chat-message:\{message\.id\}["']/u)
  assert.match(chatNotifications, /type=["']chat\.message["']/u)
  assert.match(chatNotifications, /url=f["']\/messenger\/\{message\.chat_id\}["']/u)
  assert.match(
    spec,
    /await enableAllDayQuietHours\(recipientPage,\s*recipientEmail\)/u,
    "the live notification must be delivered while its owner has active quiet hours"
  )
  assert.match(spec, /quietHoursProfile\.dnd_enabled\)\.toBe\(true\)/u)
  assert.match(spec, /quietHoursProfile\.dnd_start\)\.toMatch\(\/\^00:00/u)
  assert.match(spec, /quietHoursProfile\.dnd_end\)\.toMatch\(\/\^00:00/u)
  const quietHoursSetup = spec.indexOf(
    "await enableAllDayQuietHours(recipientPage, recipientEmail)"
  )
  const messageCreation = spec.indexOf("const messageResponsePromise")
  assert.ok(
    quietHoursSetup >= 0 && messageCreation > quietHoursSetup,
    "quiet hours must be active before the real chat message triggers notification delivery"
  )
  assert.match(
    quietHours,
    /def prepare_push_payload_for_user\([\s\S]*?if is_user_in_quiet_hours\(user, now_time=now_time\):[\s\S]*?base\[["']silent["']\]\s*=\s*True/u,
    "quiet hours change the Web Push payload without representing an in-app visibility filter"
  )
  assert.match(quietHours, /if start == end:\s*return True/u)
  assert.match(notificationsApi, /@router\.get\(["']["'],\s*response_model=/u)
  assert.match(notificationsApi, /@router\.patch\(["']\/\{notif_id\}\/read["']\)/u)
  assert.match(notificationsApi, /@router\.delete\(["']\/\{notif_id\}["']\)/u)
  assert.match(notificationsApi, /if notif\.user_id != user\.id/u)
  assert.match(notificationsBell, /markRead\(n\.id\)/u)
  assert.match(notificationsBell, /title=\{t\(["']system:notificationsBell\.markRead["']\)\}/u)
  assert.match(notificationsBell, /data-unread=\{unreadCount \? "" : undefined\}/u)

  assert.match(
    spec,
    /chat message creates one in-app notification during quiet hours and remains read and unique after reload/u
  )
  assert.match(spec, /import \{ randomUUID \} from ["']node:crypto["']/u)
  assert.match(spec, /freshPassword\(\)/u)
  assert.match(spec, /loginAs\(adminPage,\s*["']admin["']\)/u)
  assert.match(spec, /await page\.goto\(["']\/register["']\)/u)
  assert.match(spec, /registerAndLogin\(page, senderName/u)
  assert.match(spec, /registerAndLogin\(recipientPage, recipientName/u)
  assert.match(spec, /page\.getByRole\(["']button["'],\s*\{\s*name:\s*["']Новый чат["']/u)
  assert.match(spec, /getByRole\(["']option["']\)/u)
  assert.match(spec, /page\.locator\(["']#chat-message-input["']\)/u)
  assert.match(spec, /page\.locator\(["']#chat-send-btn["']\)/u)
  assert.match(spec, /\/api\/v1\/notifications\?limit=100/u)
  assert.match(spec, /findTestNotification\([\s\S]*?\.length/u)
  assert.match(spec, /unread_count/u)
  assert.match(spec, /await recipientPage\.reload\(\)/u)
  assert.ok(
    spec.includes("const expectUnreadIndicator = async"),
    "the live spec must check the bell's visual unread state"
  )
  assert.equal(
    spec.includes("await expectUnreadIndicator(recipientPage, initialUnreadCount + 1)"),
    true,
    "the bell must show unread state after the new notification persists"
  )
  assert.equal(
    spec.match(/await expectUnreadIndicator\(recipientPage, initialUnreadCount\)/gu)?.length,
    2,
    "the bell must reflect read state immediately and after reload"
  )
  assert.match(spec, /getByTitle\(["']Прочитано["']/u)
  assert.match(spec, /\/api\/v1\/notifications\/\$\{notificationId\}\/read/u)
  assert.match(spec, /read:\s*state\.matches\[0\]\?\.read/u)
  assert.match(spec, /read:\s*true,\s*unreadCount:/u)
  assert.match(spec, /deleteOnlyTestNotification/u)
  assert.match(spec, /deleteOnlyTestChat/u)
  assert.match(spec, /deleteOnlyCreatedAccount/u)
  assert.match(spec, /credentials:\s*["']same-origin["']/u)
  assert.match(spec, /["']X-CSRF-Token["']:\s*csrfToken/u)
  assert.doesNotMatch(spec, /asyncpg|sqlalchemy|nats|jetstream|webpush/iu)
})

// Topic delivery regressions share the established live-contract CI entrypoint.
import { URLSearchParams } from "node:url"
import { runInNewContext } from "node:vm"
import typescript from "typescript"

const topicsSpecUrl = new URL("./notification-topics-delivery.live.spec.ts", import.meta.url)

test("notification reads explicitly select the locale of the release marker on every page", async () => {
  const spec = await readFile(topicsSpecUrl, "utf8")
  const reader = spec.slice(
    spec.indexOf("const listAllNotifications ="),
    spec.indexOf("const waitForOnePersistedNotification =")
  )
  assert.match(reader, /new URLSearchParams\(\{ limit: "100", lang: "ru" \}\)/u)
  assert.match(reader, /if \(cursor\) query\.set\("cursor", cursor\)/u)
  assert.match(reader, /response\.headers\(\)\["content-language"\]/u)
  assert.match(reader, /\.toBe\(\s*"ru"\s*\)/u)
})

test("release delivery retains the Russian body marker and exact recipient assertions", async () => {
  const spec = await readFile(topicsSpecUrl, "utf8")
  assert.match(
    spec,
    /const releasePayload = \{ version: releaseVersion, notes_ru: releaseNotes \}/u
  )
  assert.match(spec, /expect\(releaseResult\.created\)\.toBe\(1\)/u)
  assert.match(spec, /\(row\.body \?\? ""\)\.includes\(releaseNotes\)/u)
  assert.match(spec, /expect\(repeatedRelease\.created\)\.toBe\(0\)/u)
  assert.match(spec, /expect\(native\.notificationId\)\.toBe\(notificationRow\.id\)/u)
  assert.match(spec, /expect\(native\.entityId\)\.toBe\(expected\.entityId\)/u)
  assert.doesNotMatch(spec, /notes_en: releaseNotes/u)
})

test("native delivery failures report bounded redacted observations before cleanup", async () => {
  const spec = await readFile(topicsSpecUrl, "utf8")
  const wait = spec.slice(
    spec.indexOf("const waitForNativeNotification ="),
    spec.indexOf("const assertActualDelivery =")
  )
  assert.match(
    wait,
    /catch \(error\) \{\s*await reportLivePushDeliveryObservation\(page, test\.info\(\)\.project\.name, notificationId\)\s*throw error/u
  )
  assert.match(wait, /timeout: 60_000/u)
  assert.match(wait, /\.toBe\(1\)/u)
  assert.doesNotMatch(wait, /probeSubscribe|console\.|JSON\.stringify/u)
})

test("the real notification reader keeps Russian pagination and rejects an English response", async () => {
  const spec = await readFile(topicsSpecUrl, "utf8")
  const start = spec.indexOf("const listAllNotifications =")
  const end = spec.indexOf("const waitForOnePersistedNotification =")
  assert.ok(start >= 0 && end > start)
  const compiled = typescript.transpileModule(
    `${spec.slice(start, end)}\nglobalThis.readNotifications = listAllNotifications`,
    { compilerOptions: { target: typescript.ScriptTarget.ES2022 } }
  )
  const context = {
    URLSearchParams,
    expect: (value) => ({ toBe: (expected) => assert.equal(value, expected) }),
    expectUuid: (value) => value,
  }
  runInNewContext(compiled.outputText, context)
  const urls = []
  const rows = await context.readNotifications({
    request: {
      get: async (url) => {
        urls.push(url)
        return {
          status: () => 200,
          headers: () => ({ "content-language": "ru" }),
          json: async () =>
            urls.length === 1
              ? { items: [{ id: "first" }], has_more: true, next_cursor: "next" }
              : { items: [{ id: "second" }], has_more: false },
        }
      },
    },
  })
  assert.equal(rows.length, 2)
  assert.equal(urls.length, 2)
  for (const url of urls) {
    assert.equal(new URL(url, "https://example.test").searchParams.get("lang"), "ru")
  }
  assert.equal(new URL(urls[1], "https://example.test").searchParams.get("cursor"), "next")
  await assert.rejects(
    context.readNotifications({
      request: {
        get: async () => ({
          status: () => 200,
          headers: () => ({ "content-language": "en" }),
        }),
      },
    }),
    { code: "ERR_ASSERTION" }
  )
})

// Requiring a new deletion incorrectly rejects the route's idempotent success.
const runNativeEndpointCleanup = async ({
  kind = "topics",
  body = { ok: true, removed: true },
  httpOk = true,
  nativeRevoked = true,
  nativePresent = true,
  knownEndpoint = "https://push.example.test/owned",
  nativeEndpoint = "https://push.example.test/owned",
  responseUrl = "https://stand.example.test/api/v1/push/unsubscribe",
  responseHeaders = {},
  pending = false,
  cookie = "csrf_token=owned-test-token",
  invalidJson = false,
} = {}) => {
  const name =
    kind === "chat" ? "unsubscribeOnlyNativeSubscription" : "unsubscribeOnlyNativeEndpoint"
  const spec = await readFile(
    kind === "chat" ? new URL("./push-delivery.live.spec.ts", import.meta.url) : topicsSpecUrl,
    "utf8"
  )
  const start = spec.indexOf(`const ${name} =`)
  const end = spec.indexOf(
    kind === "chat" ? "const closeContexts =" : "const findOnlyCreatedAccountId =",
    start
  )
  assert.ok(start >= 0 && end > start)
  const compiled = typescript.transpileModule(
    `${spec.slice(start, end)}\nglobalThis.cleanup = ${name}`,
    { compilerOptions: { target: typescript.ScriptTarget.ES2022 } }
  )
  const calls = []
  const events = []
  let cancelled = false
  const context = {
    document: { cookie },
    location: { origin: "https://stand.example.test" },
    URL,
    AbortController: globalThis.AbortController,
    setTimeout: globalThis.setTimeout,
    clearTimeout: globalThis.clearTimeout,
    navigator: {
      serviceWorker: {
        getRegistration: async () => ({
          pushManager: {
            getSubscription: async () =>
              nativePresent
                ? {
                    endpoint: nativeEndpoint,
                    unsubscribe: async () => {
                      calls.push("native-unsubscribe")
                      events.push("revoke")
                      return nativeRevoked
                    },
                  }
                : null,
          },
        }),
      },
    },
    fetch: async (url, options) => {
      events.push("post")
      calls.push({ url, options: JSON.parse(JSON.stringify(options)) })
      return {
        ok: httpOk,
        status: httpOk ? 200 : 500,
        url: responseUrl,
        headers: {
          get: (name) =>
            ({ "content-type": "application/json", "content-length": "30", ...responseHeaders })[
              name
            ] ?? null,
        },
        json: async () => {
          events.push("read")
          if (pending)
            return new Promise((_resolve, reject) => {
              options.signal.addEventListener(
                "abort",
                () => {
                  cancelled = true
                  reject(new Error("aborted"))
                },
                { once: true }
              )
            })
          if (invalidJson) throw new SyntaxError("invalid JSON")
          return body
        },
      }
    },
    expect: (value, message) => ({
      toBe: (expected) => assert.equal(value, expected, message),
    }),
  }
  runInNewContext(compiled.outputText, context)
  let error
  let row
  try {
    row = await context.cleanup({ evaluate: (callback, arg) => callback(arg) }, knownEndpoint)
  } catch (caught) {
    error = caught
  }
  return { calls, error, row, events, cancelled }
}

test("native cleanup reports only the existing exact-endpoint response", async () => {
  for (const removed of [true, false]) {
    const { row, error, calls } = await runNativeEndpointCleanup({
      body: { ok: true, removed, extra: "ignored" },
    })
    assert.equal(error, undefined)
    assert.equal(row, removed)
    assert.equal(calls.length, 2)
  }
  for (const options of [
    { nativeEndpoint: "https://push.example.test/rotated" },
    { nativePresent: false },
    { responseUrl: "https://elsewhere.invalid/api/v1/push/unsubscribe" },
    { responseUrl: "https://stand.example.test/api/v1/push/unsubscribe?x=1" },
  ]) {
    const { row, error } = await runNativeEndpointCleanup(options)
    assert.equal(error, undefined)
    assert.equal(row, null)
  }
})

test("chat cleanup reads a small bounded response only after native revocation", async () => {
  for (const removed of [true, false]) {
    const { row, events } = await runNativeEndpointCleanup({
      kind: "chat",
      body: { ok: true, removed, extra: "ignored" },
    })
    assert.equal(row.cleaned, true)
    assert.equal(row.row, removed)
    assert.deepEqual(events, ["post", "revoke", "read"])
  }
  for (const options of [
    { nativePresent: false },
    { nativeEndpoint: "https://push.example.test/rotated" },
    { responseUrl: "https://elsewhere.invalid/api/v1/push/unsubscribe" },
    { responseUrl: "https://stand.example.test/api/v1/push/unsubscribe?x=1" },
    { responseHeaders: { "content-length": null } },
    { responseHeaders: { "content-length": "0" } },
    { responseHeaders: { "content-length": "129" } },
    { responseHeaders: { "content-length": "30x" } },
    { responseHeaders: { "content-type": "text/html" } },
    { responseHeaders: { "content-encoding": "gzip" } },
    { body: { ok: true, removed: "false" } },
    { invalidJson: true },
  ]) {
    const { row } = await runNativeEndpointCleanup({ kind: "chat", ...options })
    assert.equal(row.cleaned, true)
    assert.equal(row.row, null)
  }
  const pending = await runNativeEndpointCleanup({ kind: "chat", pending: true })
  assert.equal(pending.row.cleaned, true)
  assert.equal(pending.row.row, null)
  assert.equal(pending.cancelled, true)
  const failed = await runNativeEndpointCleanup({ kind: "chat", nativeRevoked: false })
  assert.equal(failed.row.cleaned, false)
  assert.equal(failed.row.row, null)
  assert.deepEqual(failed.events, ["post", "revoke"])
  const rejected = await runNativeEndpointCleanup({ kind: "chat", httpOk: false })
  assert.equal(rejected.row.cleaned, false)
  assert.equal(rejected.row.row, null)
  assert.deepEqual(rejected.events, ["post", "revoke"])
})

for (const removed of [true, false]) {
  test(`native endpoint cleanup accepts confirmed server absence (removed=${removed})`, async () => {
    const { calls, error } = await runNativeEndpointCleanup({ body: { ok: true, removed } })
    assert.equal(error, undefined)
    assert.deepEqual(calls, [
      {
        url: "/api/v1/push/unsubscribe",
        options: {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": "owned-test-token",
          },
          body: '{"endpoint":"https://push.example.test/owned"}',
        },
      },
      "native-unsubscribe",
    ])
  })
}

for (const [label, options] of [
  ["HTTP failure", { httpOk: false }],
  ["server rejection", { body: { ok: false, removed: true } }],
  ["missing success", { body: { removed: true } }],
  ["nonboolean success", { body: { ok: "true", removed: true } }],
  ["numeric success", { body: { ok: 1, removed: true } }],
  ["missing removal result", { body: { ok: true } }],
  ["nonboolean removal result", { body: { ok: true, removed: "false" } }],
  ["numeric removal result", { body: { ok: true, removed: 0 } }],
  ["null removal result", { body: { ok: true, removed: null } }],
  ["null response", { body: null }],
  ["invalid JSON", { invalidJson: true }],
  ["native revocation failure", { nativeRevoked: false }],
  ["nonboolean native revocation", { nativeRevoked: "true" }],
]) {
  test(`native endpoint cleanup rejects ${label}`, async () => {
    const { calls, error } = await runNativeEndpointCleanup(options)
    assert.equal(error?.code, "ERR_ASSERTION")
    assert.equal(calls.length, 2)
    assert.equal(calls[1], "native-unsubscribe")
  })
}

test("native endpoint cleanup uses only its recorded fallback when the browser subscription is absent", async () => {
  const { calls, error } = await runNativeEndpointCleanup({
    nativePresent: false,
    body: { ok: true, removed: false },
  })
  assert.equal(error, undefined)
  assert.equal(calls.length, 1)
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    endpoint: "https://push.example.test/owned",
  })
})

test("native endpoint cleanup with no endpoint makes no mutation", async () => {
  const { calls, error } = await runNativeEndpointCleanup({
    nativePresent: false,
    knownEndpoint: null,
  })
  assert.equal(error, undefined)
  assert.deepEqual(calls, [])
})

test("native endpoint cleanup fails without CSRF and makes no mutation", async () => {
  const { calls, error } = await runNativeEndpointCleanup({ cookie: "" })
  assert.equal(error?.code, "ERR_ASSERTION")
  assert.deepEqual(calls, [])
})
