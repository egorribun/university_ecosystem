import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import { URL } from "node:url"

const specUrl = new URL("./messenger-membership-revocation.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)
const fixtureUrl = new URL("./fixtures.ts", import.meta.url)
const chatRouterUrl = new URL("../../../app/api/chat.py", import.meta.url)

const [spec, config, fixtures, chatRouter] = await Promise.all([
  readFile(specUrl, "utf8"),
  readFile(configUrl, "utf8"),
  readFile(fixtureUrl, "utf8"),
  readFile(chatRouterUrl, "utf8"),
])

test("membership-revocation live acceptance uses an owned synthetic group", () => {
  assert.match(config, /testDir:\s*["']\.\/tests\/e2e-live["']/u)
  assert.match(config, /testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u)
  assert.match(
    spec,
    /test\("a removed member loses detail, history, reactor, attachment, send, and live access"/u
  )
  assert.match(spec, /GROUP_CHAT_ACCOUNTS\.secondMember/u)
  assert.match(spec, /randomUUID\(\)/u)
  assert.match(spec, /live-membership-revocation-/u)
  assert.match(spec, /await loginAs\(page, "student"\)/u)
  assert.match(spec, /await loginAs\(removedPage, "teacher"\)/u)
  assert.match(spec, /await loginAs\(adminPage, "admin"\)/u)
  assert.match(fixtures, /secondMember:\s*\{/u)
  assert.match(
    spec,
    /expectOwnedGroup\(group, groupId, groupName, owner\.id, originalParticipants\)/u
  )
})

test("the former member proves all four reads before and after actual revocation", () => {
  assert.match(spec, /method:\s*"DELETE"/u)
  assert.match(spec, /\/api\/v1\/chats\/\$\{groupId\}\/participants\/\$\{removedUser\.id\}/u)
  assert.match(spec, /\/api\/v1\/chats\/\$\{groupId\}\/messages\/\$\{message\.id\}\/reactions/u)
  assert.match(
    spec,
    /const reactorsPath = `\/api\/v1\/chats\/\$\{groupId\}\/messages\/\$\{message\.id\}\/reactions\?emoji=/u
  )
  assert.match(spec, /removedPage\.request\.get\(`\/api\/v1\/chats\/\$\{groupId\}`\)/u)
  assert.match(
    spec,
    /removedPage\.request\.get\(`\/api\/v1\/chats\/\$\{groupId\}\/messages\?limit=100`\)/u
  )
  assert.match(spec, /removedPage\.request\.get\(reactorsPath\)/u)
  assert.match(spec, /removedPage\.request\.get\(attachmentUrl\)/u)
  assert.match(
    spec,
    /expect\(memberReads\.map\(\(response\) => response\.status\(\)\)\)\.toEqual\(\[200, 200, 200, 200\]\)/u
  )
  assert.match(spec, /revokedReads\.every\(\(response\) => isDenied\(response\.status\(\)\)\)/u)
  assert.match(spec, /return status === 403 \|\| status === 404/u)
  assert.match(
    spec,
    /revokedBodies\.some\(\(body\) => body\.includes\(attachmentContent\)\)\)\.toBe\(false\)/u
  )
  assert.match(spec, /content-disposition/u)

  const removalIndex = spec.indexOf("const removal = await sameOriginMutation(")
  const revokedReadIndex = spec.indexOf("const revokedReads = await Promise.all(")
  assert.ok(removalIndex >= 0 && revokedReadIndex > removalIndex)
  assert.match(spec, /headers:\s*\{\s*["']X-CSRF-Token["']:\s*csrfToken\s*\}/u)
  assert.match(spec, /credentials:\s*["']same-origin["']/u)
  assert.match(chatRouter, /@router\.delete\([\s\S]*?\/\{chat_id\}\/participants\/\{user_id\}/u)
  assert.match(chatRouter, /@router\.get\([\s\S]*?\/\{chat_id\}\/attachments\/\{filename:path\}/u)
})

test("refresh and WebSocket reconnect remove the former member's app, send, and fan-out access", () => {
  const scenarioStart = spec.indexOf(
    'test("a removed member loses detail, history, reactor, attachment, send, and live access"'
  )
  assert.notEqual(scenarioStart, -1, "the revocation scenario must remain explicit")
  const cleanupStart = spec.indexOf("    } finally {", scenarioStart)
  assert.ok(
    cleanupStart > scenarioStart,
    "the revocation scenario cleanup boundary must remain explicit"
  )
  const scenario = spec.slice(scenarioStart, cleanupStart)

  assert.match(scenario, /const removedSocket = observeSocket\(removedPage\)/u)
  assert.match(scenario, /await removedPage\.reload\(\)/u)
  assert.match(scenario, /removedSocket\.roomJoins[\s\S]*?toBeGreaterThan\(initialRoomJoinCount\)/u)
  assert.match(scenario, /removedPage\.locator\("#chat-message-input"\)\)\.toHaveCount\(0\)/u)
  assert.match(
    scenario,
    /removedPage\.getByText\(messageContent, \{ exact: true \}\)\)\.toHaveCount\(0\)/u
  )
  assert.match(
    scenario,
    /sameOriginMutation\([\s\S]*?removedPage[\s\S]*?"POST"[\s\S]*?postRevocationAttempt/u
  )
  assert.match(scenario, /expect\(isDenied\(revokedSend\.status\)\)\.toBe\(true\)/u)
  assert.match(scenario, /postRevocationMessage/u)
  assert.match(
    scenario,
    /expect\(\s*removedSocket\.newMessages\.some\([\s\S]*?postRevocationMessage[\s\S]*?\)\s*\)\.toBe\(false\)/u
  )
  assert.match(scenario, /const authorizedHistories/u)
  assert.match(scenario, /remainingPage\.request\.get\([\s\S]*?messages\?limit=/u)
  assert.match(scenario, /item\.content === postRevocationMessage[\s\S]*?toBe\(true\)/u)
  assert.match(
    scenario,
    /for \(const memberPage of \[page, remainingPage\]\)[\s\S]*?getByText\(messageContent, \{ exact: true \}\)\)\.toBeVisible\(\)[\s\S]*?getByText\(postRevocationMessage, \{ exact: true \}\)\)\.toBeVisible\(\)/u
  )
})

test("cleanup is owner-bounded and the live report cannot capture chat payloads", () => {
  assert.match(spec, /test\.use\(\{\s*trace:\s*["']off["'],\s*screenshot:\s*["']off["']\s*\}\)/u)
  assert.match(config, /video:\s*["']off["']/u)
  assert.match(spec, /expect\(snapshot\.created_by\)\.toBe\(ownerId\)/u)
  assert.match(spec, /allowedParticipantSets\.some\(/u)
  assert.match(
    spec,
    /const deletion = await sameOriginMutation\([\s\S]*?adminPage[\s\S]*?"DELETE"/u
  )
  assert.match(spec, /expect\(result\?\.chat_id\)\.toBe\(group\.id\)/u)
  assert.match(spec, /expect\(result\?\.deleted_attachments\)\.toBe\(1\)/u)
  assert.doesNotMatch(spec, /page\.route\(|routeWebSocket\(|\.fulfill\(|useMockApi/u)
  assert.doesNotMatch(spec, /console\.(?:log|info|debug)\(/u)
})
