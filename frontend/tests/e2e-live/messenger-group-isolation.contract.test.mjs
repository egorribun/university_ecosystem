import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import { URL } from "node:url"

const specUrl = new URL("./messenger-group-isolation.live.spec.ts", import.meta.url)
const fixtureUrl = new URL("./fixtures.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const listRouteUrl = new URL("../../src/routes/_auth/messenger.tsx", import.meta.url)
const detailRouteUrl = new URL("../../src/routes/_auth/messenger.$chatId.tsx", import.meta.url)
const chatApiUrl = new URL("../../src/api/chat.ts", import.meta.url)
const adminSeedUrl = new URL("../../../scripts/seed_admin_data.py", import.meta.url)
const standUrl = new URL("../../../scripts/live_stand.py", import.meta.url)
const versionUrl = new URL("../../../app/core/versioning.py", import.meta.url)
const publicApiUrl = new URL("../../../app/api/public/__init__.py", import.meta.url)
const chatRouterUrl = new URL("../../../app/api/chat.py", import.meta.url)
const chatSchemasUrl = new URL("../../../app/schemas/chat.py", import.meta.url)
const creationServiceUrl = new URL(
  "../../../app/services/chat/creation_service.py",
  import.meta.url
)
const queryServiceUrl = new URL("../../../app/services/chat/query_service.py", import.meta.url)
const websocketClientUrl = new URL("../../../services/ws-hub/pkg/hub/client.go", import.meta.url)
const websocketHubUrl = new URL("../../../services/ws-hub/pkg/hub/hub.go", import.meta.url)

const [
  spec,
  fixtures,
  config,
  listRoute,
  detailRoute,
  chatApi,
  adminSeed,
  stand,
  version,
  publicApi,
  chatRouter,
  chatSchemas,
  creationService,
  queryService,
  websocketClient,
  websocketHub,
] = await Promise.all([
  readFile(specUrl, "utf8"),
  readFile(fixtureUrl, "utf8"),
  readFile(configUrl, "utf8"),
  readFile(listRouteUrl, "utf8"),
  readFile(detailRouteUrl, "utf8"),
  readFile(chatApiUrl, "utf8"),
  readFile(adminSeedUrl, "utf8"),
  readFile(standUrl, "utf8"),
  readFile(versionUrl, "utf8"),
  readFile(publicApiUrl, "utf8"),
  readFile(chatRouterUrl, "utf8"),
  readFile(chatSchemasUrl, "utf8"),
  readFile(creationServiceUrl, "utf8"),
  readFile(queryServiceUrl, "utf8"),
  readFile(websocketClientUrl, "utf8"),
  readFile(websocketHubUrl, "utf8"),
])

test("group isolation uses stable demo accounts and the owner-checked live seed", () => {
  assert.match(fixtures, /student:\s*\{\s*email: "test@university\.dev"/u)
  assert.match(fixtures, /teacher:\s*\{\s*email: "olga\.morozova@university\.dev"/u)
  assert.match(fixtures, /secondMember:\s*\{\s*email: "ivan\.sokolov@university\.dev"/u)
  assert.match(fixtures, /nonMember:\s*\{\s*email: "sergey\.lebedev@university\.dev"/u)
  assert.match(fixtures, /LIVE_GROUP_CHAT_NAME = "University Ecosystem live Messenger isolation"/u)

  assert.match(adminSeed, /"olga\.morozova@university\.dev"[\s\S]{0,220}UserRole\.TEACHER/u)
  assert.match(adminSeed, /"ivan\.sokolov@university\.dev"[\s\S]{0,220}UserRole\.STUDENT/u)
  assert.match(adminSeed, /"sergey\.lebedev@university\.dev"[\s\S]{0,220}UserRole\.TEACHER/u)
  assert.match(
    stand,
    /SEED_SCRIPTS = \(\s*"scripts\/seed_demo_data\.py",\s*"scripts\/seed_admin_data\.py",\s*"scripts\/seed_live_authorization\.py",?\s*\)/u
  )
  assert.match(stand, /seed_parser\.add_argument\("--demo", action="store_true", required=True\)/u)
  assert.match(spec, /await loginAs\(page, "student"\)/u)
  assert.match(spec, /await loginAs\(teacherPage, "teacher"\)/u)
  assert.match(spec, /GROUP_CHAT_ACCOUNTS\.secondMember\.email/u)
  assert.match(spec, /GROUP_CHAT_ACCOUNTS\.nonMember\.email/u)
  assert.match(
    spec,
    /new Set\(\[owner\.id, teacher\.id, secondMember\.id, outsider\.id\]\)\.size\)\.toBe\(4\)/u
  )
})

test("real chat routes return exact group membership and deny outsider reads", () => {
  assert.match(version, /API_V1_PREFIX[^=\n]*=\s*["']\/api\/v1["']/u)
  assert.match(publicApi, /router\.include_router\(chat_router\)/u)
  assert.match(chatRouter, /router\s*=\s*APIRouter\(prefix="\/chats"/u)
  assert.match(chatRouter, /@router\.post\([\s\S]*?"\/groups"[\s\S]*?async def create_group/u)
  assert.match(chatRouter, /@router\.get\([\s\S]*?"\/\{chat_id\}"[\s\S]*?async def get_chat/u)
  assert.match(chatRouter, /return await query_service\.get_chat_details\(chat_id, current_user/u)
  assert.match(chatSchemas, /class GroupChatCreate\([\s\S]*?participant_ids: list\[UUID\]/u)
  assert.match(chatSchemas, /participants: list\[ChatParticipant\]/u)
  assert.match(creationService, /async def create_group\([\s\S]*?member_ids: list\[uuid\.UUID\]/u)
  assert.match(
    creationService,
    /total = len\(member_ids\) \+ 1[\s\S]*?create_group\(user, clean_name, members\)/u
  )
  assert.match(
    queryService,
    /async def get_chat_details\([\s\S]*?participant_ids = \{p\.id for p in chat\.participants\}[\s\S]*?if user\.id not in participant_ids:[\s\S]*?raise_forbidden/u
  )
  assert.match(spec, /deniedChatResponse\.status\(\)\)\.toBe\(403\)/u)
  assert.match(
    spec,
    /expectGroupOwnedByMembers\(group, owner\.id, \[owner\.id, teacher\.id, secondMember\.id\]\)/u
  )
})

test("live WebSocket assertions exercise real group fan-out without transport mocks", () => {
  assert.match(listRoute, /createFileRoute\("\/_auth\/messenger"\)/u)
  assert.match(detailRoute, /createFileRoute\("\/_auth\/messenger\/\$chatId"\)/u)
  assert.match(chatApi, /client\.post<Chat>\("\/chats\/groups"/u)
  assert.match(
    chatApi,
    /const encodePathIdentifier = \(identifier: string\): string => encodeURIComponent\(identifier\)/u
  )
  assert.match(
    chatApi,
    /const url = `\/chats\/\$\{encodePathIdentifier\(chatId\)\}`[\s\S]*?client\.get<Chat>\(url/u
  )
  assert.match(spec, /test\.use\(\{ trace: "off", screenshot: "off" \}\)/u)
  assert.match(config, /video:\s*"off"/u)
  assert.match(spec, /page\.on\("websocket"/u)
  assert.match(spec, /socket\.on\("framesent"/u)
  assert.match(spec, /socket\.on\("framereceived"/u)
  assert.match(spec, /roomJoins\.filter\(\(room\) => room === chatId\)/u)
  assert.match(spec, /nonMemberSocket\.roomJoins[\s\S]*?toBeGreaterThan\(0\)/u)
  assert.match(
    spec,
    /eventsForMessage\(nonMemberSocket, chatId, sentMessage\.id\)\)\.toEqual\(\[\]\)/u
  )
  assert.match(spec, /eventsForMessage\(socket, chatId, sentMessage\.id\)/u)
  assert.match(spec, /message_edited[\s\S]*?message_deleted/u)
  const joinStart = websocketClient.indexOf("func (c *Client) handleJoin(")
  const joinEnd = websocketClient.indexOf("func (c *Client) prepareAuthorizedRoomJoin(", joinStart)
  assert.ok(joinStart >= 0 && joinEnd > joinStart, "the room join handler must exist")
  const joinHandler = websocketClient.slice(joinStart, joinEnd)
  assert.match(
    joinHandler,
    /authorized, retryConnection := c\.authorizeRoomJoinWithStatus\(ctx, msg\.Room,[\s\S]*?return c\.prepareAuthorizedRoomJoin\(ctx, msg, decision\)/u
  )
  assert.match(
    joinHandler,
    /if !authorized \{\s*if retryConnection && c\.roomJoinContextActive\(ctx\) \{[\s\S]*?c\.closeTransportWithControlFrame\(websocket\.CloseTryAgainLater, "room admission temporarily unavailable"\)\s*c\.cancelConnection\(\)\s*return\s*\}\s*c\.rejectUnauthorizedRoomJoin\(ctx, msg\.Room\)\s*return\s*\}\s*c\.finishAuthorizedRoomJoin\(ctx, msg, decision\)/u
  )
  assert.match(
    websocketClient,
    /admission, admitted := c\.roomJoinAdmissionSnapshot\(\)\s*if !admitted \{\s*return false, true\s*\}/u
  )
  assert.match(
    websocketClient,
    /allowed, refreshed := c\.Hub\.authorizeRoomJoin\(ctx, c\.UserID, room, pending\)/u
  )
  assert.match(websocketHub, /return h\.authClient\.CanJoinRoom\(ctx, userID, room\)/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
  assert.doesNotMatch(spec, /page\.route\(|routeWebSocket\(|fulfill\(|useMockApi/u)
  assert.doesNotMatch(spec, /page\.request\.(?:post|put|patch|delete)\(/u)
})

test("authenticated non-member cannot send a message into the private group", () => {
  assert.ok(
    /const nonMemberAttempt = `live-group-outsider-\$\{crypto\.randomUUID\(\)\}`/u.test(spec),
    "the denied write must use a unique synthetic marker"
  )
  assert.ok(
    /nonMemberPage\.evaluate\(\s*async[\s\S]*?fetch\(`\/api\/v1\/chats\/\$\{chatId\}\/messages`/u.test(
      spec
    ),
    "the authenticated browser context must attempt the actual send endpoint"
  )
  assert.ok(
    /headers:\s*\{\s*["']X-CSRF-Token["']:\s*csrfToken\s*\}/u.test(spec),
    "the request must pass CSRF so membership authorization is the reason for denial"
  )
  assert.ok(
    /expect\(nonMemberSendAttempt\.csrfAvailable\)\.toBe\(true\)/u.test(spec) &&
      /expect\(nonMemberSendAttempt\.status\)\.toBe\(403\)/u.test(spec),
    "the test must prove a CSRF-valid send attempt is rejected as forbidden"
  )
  assert.ok(
    /expect\(await memberHistoryContains\(memberPage,\s*chatId,\s*nonMemberAttempt\)\)\.toBe\(false\)/u.test(
      spec
    ) && /event\.content === nonMemberAttempt[\s\S]*?\)\.toBe\(false\)/u.test(spec),
    "the unique marker must be absent from member history and WebSocket deliveries"
  )
  const attemptStart = spec.indexOf("const nonMemberSendAttempt =")
  const attemptEnd = spec.indexOf("for (const memberPage", attemptStart)
  assert.ok(attemptStart >= 0 && attemptEnd > attemptStart)
  const sendAttempt = spec.slice(attemptStart, attemptEnd)
  assert.match(sendAttempt, /return \{ csrfAvailable: true, status: response\.status \}/u)
  assert.doesNotMatch(sendAttempt, /console\.|response\.(?:text|json)\(/u)
  assert.doesNotMatch(spec, /console\.(?:log|info|debug)\(/u)
})

// Execute the actual TypeScript frame decoder, not a duplicate test implementation.
const { default: ts } = await import("typescript")
const { runInNewContext } = await import("node:vm")
function groupDecoder(source = spec) {
  const start = source.indexOf("type JsonRecord =")
  const end = source.indexOf("async function getCurrentUser(")
  assert.ok(start >= 0 && end > start)
  const compiled = ts.transpileModule(source.slice(start, end), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.None },
  }).outputText
  const context = {}
  runInNewContext(compiled + "\nglobalThis.decode = findGroupMessageEvents", context)
  return (value) => JSON.parse(JSON.stringify(context.decode(value)))
}

test("group observer retains replay ordering and exact sender/chat identity from real hub envelopes", () => {
  const decode = groupDecoder()
  const envelope = {
    seq: 31,
    replayed: true,
    payload: {
      type: "new_message",
      chat_id: "group-a",
      message: {
        id: "message-a",
        chat_id: "group-a",
        sender_id: "owner-a",
        content: "synthetic",
      },
    },
  }
  assert.deepEqual(decode([envelope]), [
    {
      type: "new_message",
      chatId: "group-a",
      messageId: "message-a",
      content: "synthetic",
      senderId: "owner-a",
      messageChatId: "group-a",
      sequence: 31,
      replayed: true,
    },
  ])
  assert.equal(decode({ ...envelope, replayed: false })[0].replayed, false)
  assert.equal(decode({ ...envelope, seq: "31" })[0].sequence, undefined)
  assert.deepEqual(decode(null), [])
  assert.deepEqual(decode({ payload: { type: "new_message", chat_id: "group-a" } }), [])
  assert.deepEqual(
    decode({
      payload: {
        type: "message_edited",
        chat_id: "group-a",
        message_id: "message-a",
        content: "edited",
        edited_at: "2026-11-14T00:00:00Z",
      },
    })[0],
    {
      type: "message_edited",
      chatId: "group-a",
      messageId: "message-a",
      content: "edited",
      editedAt: "2026-11-14T00:00:00Z",
      replayed: false,
    }
  )
})

function assertGroupReconnect(source) {
  for (const marker of [
    "await teacherContext.setOffline(true)",
    "teacherPage.evaluate(() => navigator.onLine)).toBe(false)",
    "expect(eventsForMessage(teacherSocket, chatId, item.id)).toEqual([])",
    "await teacherContext.setOffline(false)",
    "teacherSocket.sessions.slice(previousSessionCount)",
    "session.resumeRooms.includes(chatId)",
    "expect((await historyPromise).ok()).toBe(true)",
    "expect(replay.map((event) => event.messageId)).toEqual(missedIds)",
    "content: missed[index]!.content, replayed: true",
    "expect(Number.isSafeInteger(event.sequence)).toBe(true)",
    "content: after.content, replayed: false",
    "expect(afterFrame.sequence!).toBeGreaterThan(replay[1]!.sequence!)",
    "expect(eventsForMessage(nonMemberSocket, chatId, id)).toEqual([])",
    "expect(eventsForMessage(teacherSocket, chatId, item.id)).toHaveLength(1)",
  ]) {
    assert.ok(
      source.replace(/\s+/gu, "").includes(marker.replace(/\s+/gu, "")),
      `missing group reconnect acceptance: ${marker}`
    )
  }
  assert.ok(
    source.indexOf("await teacherContext.setOffline(true)") < source.indexOf("const missed =")
  )
  assert.ok(
    source.indexOf("const missed =") < source.indexOf("await teacherContext.setOffline(false)")
  )
  assert.doesNotMatch(
    source,
    /test\.setTimeout|test\.slow|timeout:|retries:|routeWebSocket|page\.route\(/u
  )
  assert.equal((source.match(/test\("group events reach both members/g) ?? []).length, 1)
}

test("existing group acceptance covers real offline replay without changing collection or budgets", () => {
  assertGroupReconnect(spec)
})

test("group reconnect acceptance guards reject missing replay, isolation and dedup evidence", () => {
  for (const marker of [
    "await teacherContext.setOffline(true)",
    "expect(replay.map((event) => event.messageId)).toEqual(missedIds)",
    "content: missed[index]!.content, replayed: true",
    "expect(eventsForMessage(nonMemberSocket, chatId, id)).toEqual([])",
    "expect(eventsForMessage(teacherSocket, chatId, item.id)).toHaveLength(1)",
  ]) {
    const candidate = spec.replace(
      new RegExp(
        marker
          .split(/\s+/u)
          .map((part) => part.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&"))
          .join("\\s*"),
        "u"
      ),
      ""
    )
    assert.notEqual(candidate, spec)
    assert.throws(() => assertGroupReconnect(candidate), { name: "AssertionError" })
  }
})
