import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import { URL } from "node:url"

const specUrl = new URL("./messenger-realtime.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)

const [spec, config] = await Promise.all([readFile(specUrl, "utf8"), readFile(configUrl, "utf8")])

test("live Messenger realtime acceptance runs on desktop and mobile without saved credentials", () => {
  assert.match(config, /testDir:\s*["']\.\/tests\/e2e-live["']/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
  assert.match(config, /name:\s*["']desktop["']/u)
  assert.match(config, /name:\s*["']mobile["']/u)
  assert.match(config, /viewport:\s*\{\s*width:\s*1440,\s*height:\s*900\s*\}/u)
  assert.match(config, /viewport:\s*\{\s*width:\s*390,\s*height:\s*844\s*\}/u)
  assert.match(spec, /test\.use\(\{\s*trace:\s*["']off["'],\s*screenshot:\s*["']off["']\s*\}\)/u)
  assert.match(config, /video:\s*["']off["']/u)
  assert.match(spec, /process\.env\.LIVE_BASE_URL/u)
  assert.doesNotMatch(spec, /console\.(?:log|info|debug)\(/u)
})

test("each realtime flow uses independent, differently authenticated student and teacher contexts", () => {
  assert.match(spec, /browser\.newContext\(/u)
  assert.match(spec, /receiverContext\.newPage\(\)/u)
  assert.match(spec, /await loginAs\(page, ["']student["']\)/u)
  assert.match(spec, /await loginAs\(receiverPage, ["']teacher["']\)/u)
  assert.match(spec, /crypto\.randomUUID\(\)/u)
  assert.match(spec, /\/api\/v1\/users\/me/u)
  assert.match(spec, /expect\(student\.role\)\.toBe\(["']student["']\)/u)
  assert.match(spec, /expect\(teacher\.role\)\.toBe\(["']teacher["']\)/u)
  assert.match(spec, /expect\(receiver\.id\)\.not\.toBe\(sender\.id\)/u)
  assert.match(spec, /expect\(teacher\.id\)\.not\.toBe\(student\.id\)/u)
})

test("message, edit, delete, and reaction assertions observe real server responses and WebSocket frames", () => {
  assert.match(spec, /page\.on\(["']websocket["']/u)
  assert.match(spec, /socket\.on\(["']framesent["']/u)
  assert.match(spec, /socket\.on\(["']framereceived["']/u)
  assert.match(spec, /hasRoomJoin\(parseFrame\(payload\), chatId\)/u)
  assert.match(
    spec,
    /new URL\(response\.url\(\)\)\.pathname === `\/api\/v1\/chats\/\$\{chatId\}\/messages`/u
  )
  assert.match(spec, /sender_id:\s*student\.id/u)
  assert.match(
    spec,
    /sender_id:\s*student\.id[\s\S]*?message:\s*\{[\s\S]*?senderId:\s*student\.id/u
  )
  assert.match(
    spec,
    /expect\(receiverMessages\)\.toContainEqual\(expect\.objectContaining\(expectedFrame\)\)/u
  )
  assert.match(spec, /expect\(renderedMessage\)\.toHaveCount\(1\)/u)
  assert.match(spec, /type === "message_edited"[\s\S]*?type === "message_deleted"/u)
  assert.match(spec, /request\.method\(\) === "PATCH"/u)
  assert.match(spec, /request\.method\(\) === "DELETE"/u)
  assert.match(spec, /senderReactions\.filter\([\s\S]*?frame\.userId === receiver\.id/u)
  assert.match(spec, /senderMessageHistory\?\.reactions/u)
  assert.match(spec, /receiverMessageHistory\?\.reactions/u)
})

test("deleted message tombstones keep authorized history visible without reaction controls", () => {
  const tombstoneStart = spec.indexOf(
    'test("a message is delivered, edited, and tombstoned in the other authenticated session"'
  )
  assert.notEqual(tombstoneStart, -1, "the tombstone scenario must remain explicit")
  const nextScenario = spec.indexOf(
    'test("two direct-message deliveries keep sequence order',
    tombstoneStart
  )
  assert.notEqual(nextScenario, -1, "the tombstone scenario boundary must remain explicit")
  const tombstoneScenario = spec.slice(tombstoneStart, nextScenario)

  assert.match(tombstoneScenario, /request\.method\(\) === "POST"[\s\S]*?\/reactions/u)
  assert.match(
    tombstoneScenario,
    /getByRole\("button", \{ name: "Отреагировать 👍", exact: true \}\)/u
  )
  assert.match(
    tombstoneScenario,
    /const tombstone = messageLog\.getByText\("Сообщение удалено", \{ exact: true \}\)[\s\S]{0,100}await expect\(tombstone\)\.toBeVisible\(\)/u
  )
  assert.match(
    tombstoneScenario,
    /tombstoneRow\.getByRole\("button", \{ name: \/реакци\/i \}\)[\s\S]{0,100}\.toHaveCount\(0\)/u
  )
  assert.match(
    tombstoneScenario,
    /page\.request\.get\(`\/api\/v1\/chats\/\$\{chatId\}\/messages\?limit=50`\)/u
  )
  assert.match(
    tombstoneScenario,
    /receiverPage\.request\.get\(`\/api\/v1\/chats\/\$\{chatId\}\/messages\?limit=50`\)/u
  )
  assert.match(tombstoneScenario, /deleted_at:\s*string \| null/u)
  assert.match(
    tombstoneScenario,
    /expect\(senderTombstone\)\.toMatchObject\(\{ id: sentMessage\.id, content: "" \}\)/u
  )
  assert.match(tombstoneScenario, /expect\(senderTombstone\?\.deleted_at\)\.toBeTruthy\(\)/u)
  assert.match(
    tombstoneScenario,
    /expect\(receiverTombstone\)\.toMatchObject\(\{ id: sentMessage\.id, content: "" \}\)/u
  )
  assert.match(tombstoneScenario, /expect\(receiverTombstone\?\.deleted_at\)\.toBeTruthy\(\)/u)
  assert.match(tombstoneScenario, /senderTombstone\?\.reactions/u)
  assert.match(tombstoneScenario, /receiverTombstone\?\.reactions/u)
})

test("removing a reaction is delivered over WebSocket and clears both members' server history", () => {
  const reactionStart = spec.indexOf(
    'test("a receiver reaction is delivered to the sender over the live WebSocket"'
  )
  assert.notEqual(reactionStart, -1, "the reaction scenario must remain explicit")
  const replyStart = spec.indexOf(
    'test("a sender reply preserves its parent identity',
    reactionStart
  )
  assert.notEqual(replyStart, -1, "the following scenario boundary must remain explicit")
  const reactionScenario = spec.slice(reactionStart, replyStart)
  assert.match(reactionScenario, /frame\.action === "removed"/u)
  assert.match(reactionScenario, /senderAfterRemovalHistory[\s\S]{0,220}toEqual\(\[\]\)/u)
  assert.match(reactionScenario, /receiverAfterRemovalHistory[\s\S]{0,220}toEqual\(\[\]\)/u)
})

test("ordered live deliveries remain exactly once across reconnect and history refresh", () => {
  assert.match(
    spec,
    /two direct-message deliveries keep sequence order and deduplicate after reconnect/u
  )
  assert.match(spec, /const messageIds = \[first\.id, second\.id\]/u)
  assert.match(
    spec,
    /orderedDeliveries\.map\(\(frame\) => frame\.message\.id\)\)\.toEqual\(messageIds\)/u
  )
  assert.match(spec, /expect\(firstSequence\)\.toBeLessThan\(secondSequence\)/u)
  assert.match(spec, /await receiverContext\.setOffline\(true\)/u)
  assert.match(spec, /await receiverContext\.setOffline\(false\)/u)
  assert.match(spec, /historyRefetchPromise/u)
  assert.match(spec, /deliveriesForMessages\(\)\)\.toHaveLength\(2\)/u)
  assert.match(
    spec,
    /receiverLog\.getByText\(message\.content, \{ exact: true \}\)\)\.toHaveCount\(1\)/u
  )
})

test("reply and forward live events retain their server-owned relationship metadata", () => {
  assert.match(spec, /a sender reply preserves its parent identity and reaches the receiver/u)
  assert.match(spec, /reply_to:\s*\{\s*id:\s*createdParent\.id/u)
  assert.match(spec, /frame\.message\.replyToId === createdParent\.id/u)
  assert.match(
    spec,
    /forwarding through the current-chat modal preserves attribution and reaches the receiver/u
  )
  assert.match(spec, /forwarded_from_name:\s*senderName/u)
  assert.match(spec, /frame\.message\.forwardedFromName === senderName/u)
  const forwardingStart = spec.indexOf('test("forwarding through the current-chat modal')
  assert.notEqual(forwardingStart, -1, "forwarding scenario must remain explicit")
  const forwardingScenario = spec.slice(forwardingStart)
  assert.match(forwardingScenario, /receiverMessages\.filter\(/u)
  assert.match(forwardingScenario, /frame\.message\.id === createdForward\.id/u)
  assert.match(forwardingScenario, /\.toHaveLength\(1\)/u)
})

test("cleanup deletes only exact sender-owned test messages and never a reusable seeded chat", () => {
  assert.match(spec, /async function deleteOwnedLiveMessage\([\s\S]*?message: CreatedLiveMessage/u)
  assert.match(spec, /`\/api\/v1\/chats\/\$\{chatId\}\/messages\/\$\{message\.id\}`/u)
  assert.match(
    spec,
    /async function deleteOwnedForwardedLiveMessage\([\s\S]*?message: CreatedLiveMessage/u
  )
  assert.match(spec, /`\/api\/v1\/chats\/\$\{chatId\}\/messages\/\$\{message\.id\}`/u)
  assert.match(
    spec,
    /for \(const message of createdMessages\)[\s\S]*?deleteOwnedLiveMessage\(page, senderLog, chatId, message\)/u
  )
  assert.match(spec, /receiverContext\.close\(\)/u)
  assert.doesNotMatch(spec, /DELETE[^\n]*\/api\/v1\/chats\/\$\{chatId\}(?:["'`]|\s)/u)
  assert.doesNotMatch(spec, /page\.route\(|routeWebSocket\(|route\.fulfill\(|useMockApi/u)
})
