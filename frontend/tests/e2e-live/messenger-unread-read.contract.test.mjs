import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import { URL } from "node:url"

const specUrl = new URL("./messenger-unread-read.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const chatApiUrl = new URL("../../src/api/chat.ts", import.meta.url)
const chatRouterUrl = new URL("../../../app/api/chat.py", import.meta.url)
const commandServiceUrl = new URL("../../../app/services/chat/command_service.py", import.meta.url)
const wsSchemaUrl = new URL("../../src/api/schemas/wsMessage.ts", import.meta.url)
const contactListUrl = new URL("../../src/components/messenger/ContactList.tsx", import.meta.url)

test("Messenger live unread-to-read acceptance uses owned users, REST state, and real WS", async () => {
  let spec
  try {
    spec = await readFile(specUrl, "utf8")
  } catch {
    assert.fail("a dedicated live Messenger unread-to-read scenario must exist")
  }

  const [config, chatApi, chatRouter, commandService, wsSchema, contactList] = await Promise.all([
    readFile(configUrl, "utf8"),
    readFile(chatApiUrl, "utf8"),
    readFile(chatRouterUrl, "utf8"),
    readFile(commandServiceUrl, "utf8"),
    readFile(wsSchemaUrl, "utf8"),
    readFile(contactListUrl, "utf8"),
  ])
  const requireMatch = (pattern, message, source = spec) => assert.ok(pattern.test(source), message)

  requireMatch(/testDir:\s*["']\.\/tests\/e2e-live["']/u, "live config owns the spec", config)
  requireMatch(/testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u, "spec is discoverable", config)
  requireMatch(
    /test\.use\(\{\s*trace:\s*["']off["'],\s*screenshot:\s*["']off["'],\s*video:\s*["']off["']/u,
    "credentials and chat payloads are excluded from persisted browser artifacts"
  )
  requireMatch(/randomUUID\(\)/u, "each run creates fresh account identities")
  requireMatch(/live-messenger-unread-sender-/u, "sender identity is run-unique")
  requireMatch(/live-messenger-unread-receiver-/u, "receiver identity is run-unique")
  requireMatch(/live-messenger-unread-peer-/u, "second chat peer identity is run-unique")
  requireMatch(/stubBreachedPasswordLookup\(page\)/u, "registration password checks stay local")
  requireMatch(/pathname\.endsWith\(["']\/auth\/register["']\)/u, "users register in the app")
  requireMatch(/\/api\/v1\/users\/me/u, "new account identities are confirmed")
  requireMatch(
    /new Set\(\[sender\.id, receiver\.id, peer\.id\]\)\.size\)\.toBe\(3\)/u,
    "all three generated chat participants have distinct identities"
  )
  requireMatch(
    /registerSyntheticUser\(currentPeerPage, peer\)/u,
    "the second chat uses a real owned peer"
  )
  requireMatch(
    /createDirectChat\(receiverPage, peer\.fullName/u,
    "the receiver has a second independent direct chat"
  )
  requireMatch(
    /sendLiveMessage\(\s*currentPeerPage,[\s\S]{0,100}activeSecondChatId/u,
    "the second unread message is sent by its own chat participant"
  )

  requireMatch(/page\.on\(["']websocket["']/u, "the sender observes the real WebSocket")
  requireMatch(/socket\.on\(["']framereceived["']/u, "server frames are observed from the socket")
  requireMatch(/type === ["']read["']/u, "read receipts are decoded from server frames")
  requireMatch(
    /receiverPage\.goto\(["']\/dashboard["']\)[\s\S]*?sendLiveMessage\(/u,
    "the receiver is away from the DM while the unread message is sent"
  )
  requireMatch(/\/api\/v1\/chats\?limit=100/u, "unread is read from the receiver's real chat list")
  requireMatch(/unread_count[\s\S]{0,80}\.toBe\(1\)/u, "the server reports one unread DM")
  requireMatch(
    /read_status[\s\S]{0,80}\.toBe\(false\)/u,
    "the message remains unread before the chat opens"
  )
  requireMatch(
    /messenger-contact-\$\{activeChatId\}/u,
    "the generated chat's real list row is inspected"
  )
  requireMatch(/getByLabel\(\/1 непрочитано\//u, "the UI presents the unread badge")
  requireMatch(/receiverPage\.reload\(\)/u, "the unread state is checked after a real reload")
  requireMatch(
    /getChatListItem\(receiverPage, activeSecondChatId\)[\s\S]{0,180}\.toBe\(1\)/u,
    "the second DM retains its own unread count after reload"
  )

  requireMatch(
    /\/api\/v1\/chats\/\$\{activeChatId\}\/read/u,
    "opening the chat uses the read endpoint"
  )
  requireMatch(
    /unread_count[\s\S]{0,80}\.toBe\(0\)/u,
    "the server clears unread state after reading"
  )
  requireMatch(
    /getChatListItem\(receiverPage, activeSecondChatId\)[\s\S]{0,220}\.toBe\(1\)/u,
    "reading the first chat does not clear the second chat unread count"
  )
  requireMatch(
    /getMessage\(receiverPage, activeSecondChatId, secondMessage\.id\)[\s\S]{0,180}\.toBe\(false\)/u,
    "the second message remains unread until its own chat opens"
  )
  requireMatch(
    /secondReceiverChatRow\.getByLabel\(\/1 непрочитано\/u\)\)\.toHaveCount\(1\)/u,
    "the second unread badge remains visible after opening the first DM"
  )
  requireMatch(
    /toContainEqual\(expect\.objectContaining\(\{ userId: receiver\.id \}\)\)/u,
    "the sender receives the receiver's read identity"
  )
  requireMatch(
    /getByRole\(["']img["'],\s*\{\s*name:\s*["']Прочитано получателем["']/u,
    "the read receipt is visible to the message sender"
  )

  requireMatch(/deleteOwnedLiveMessage\(/u, "the generated message is deleted by its sender")
  requireMatch(/deleteOnlyCreatedChat\(/u, "cleanup targets the exact generated chat")
  requireMatch(/deleteOnlyCreatedAccount\(/u, "cleanup targets only generated account ids")
  requireMatch(
    /deleteOwnedLiveMessage\(peerPage!, peerLog!, secondChatId!, message\)/u,
    "the second chat message cleanup uses its generating peer and exact chat id"
  )
  requireMatch(
    /deleteOnlyCreatedChat\(adminPage!, secondChatId!\)/u,
    "cleanup removes only the second generated chat"
  )
  requireMatch(
    /deleteOnlyCreatedAccount\(adminPage!, peer\)/u,
    "cleanup resolves and removes only the second generated peer account"
  )
  requireMatch(/X-CSRF-Token/u, "administrative cleanup uses CSRF")
  assert.doesNotMatch(spec, /useMockApi|page\.route\(|routeWebSocket\(|route\.fulfill\(/u)

  requireMatch(
    /markRead:\s*async \(chatId: string\)[\s\S]{0,120}client\.post\(`/u,
    "the frontend uses the real mark-read mutation",
    chatApi
  )
  requireMatch(
    /@router\.post\([\s\S]{0,100}\{chat_id\}\/read/u,
    "the backend exposes the authenticated read endpoint",
    chatRouter
  )
  requireMatch(
    /"type":\s*"read"[\s\S]{0,180}"user_id":\s*str\(user\.id\)/u,
    "the backend broadcasts the reader identity after marking messages",
    commandService
  )
  requireMatch(
    /type:\s*v\.literal\(["']read["']\)/u,
    "the websocket catalog validates read frames",
    wsSchema
  )
  requireMatch(
    /messenger:aria\.unread/u,
    "the contact list exposes an accessible unread badge",
    contactList
  )
})
