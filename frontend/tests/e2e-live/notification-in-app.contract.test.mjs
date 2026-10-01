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
    /await enableAllDayQuietHours\(recipientPage\)/u,
    "the live notification must be delivered while its owner has active quiet hours"
  )
  assert.match(spec, /quietHoursProfile\.dnd_enabled\)\.toBe\(true\)/u)
  assert.match(spec, /quietHoursProfile\.dnd_start\)\.toMatch\(\/\^00:00/u)
  assert.match(spec, /quietHoursProfile\.dnd_end\)\.toMatch\(\/\^00:00/u)
  const quietHoursSetup = spec.indexOf("await enableAllDayQuietHours(recipientPage)")
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
