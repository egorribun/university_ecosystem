import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"

test("live messenger reconnect replays missed events exactly once and resumes in sequence", async () => {
  const spec = await readFile(
    new URL("../tests/e2e-live/messenger-reconnect.live.spec.ts", import.meta.url),
    "utf8"
  )

  const offline = spec.indexOf("setOffline(true)")
  const online = spec.indexOf("setOffline(false)")
  assert.ok(
    offline >= 0 && online > offline,
    "the real browser context must lose and restore network"
  )
  assert.match(spec, /socket\.on\(["']framesent["']/u)
  assert.match(spec, /socket\.on\(["']framereceived["']/u)
  assert.match(spec, /resume_token/u)
  assert.match(spec, /messages.*chatId|chatId.*messages/u)
  assert.match(spec, /toHaveCount\(1\)/u)
  assert.ok(
    /secondMemberSocket\s*=\s*observeSocket/u.test(spec),
    "a second authenticated group member must observe the live socket event"
  )
  const missedMessage = spec.indexOf("const missedWhileOfflineMessage = await sendMessage")
  assert.ok(
    offline >= 0 && missedMessage > offline && online > missedMessage,
    "the sender must publish a real message while the receiver context is offline"
  )
  assert.ok(
    /eventsForRoom\(secondMemberSocket,\s*chatId,\s*missedWhileOfflineMessage\.id\)/u.test(spec),
    "a still-connected group member must observe the offline-period message before reconnect"
  )
  assert.ok(
    /expect\(historyRefetch\.ok\(\)\)\.toBe\(true\)/u.test(spec),
    "reconnection must also reconcile the missed message through the real history endpoint"
  )
  assert.ok(
    /receiverLog\.getByText\(missedWhileOfflineContent,\s*\{\s*exact:\s*true\s*\}\)\)\.toHaveCount\(1\)/u.test(
      spec
    ),
    "the replayed message must appear exactly once in the receiver's rendered history"
  )
  assert.ok(
    /expect\(missedDelivery\.replayed\)\.toBe\(true\)/u.test(spec),
    "the offline-period message must be observed as a replay frame"
  )
  assert.ok(
    /missedDelivery\.sequence\s*\?\?\s*0\)\.toBeGreaterThan\(initialDelivery\.sequence\s*\?\?\s*0/u.test(
      spec
    ),
    "the missed frame must advance the room sequence after the pre-disconnect frame"
  )
  assert.ok(
    /afterReconnectDelivery\.sequence\s*\?\?\s*0\)\.toBeGreaterThan\(\s*missedDelivery\.sequence\s*\?\?\s*0/u.test(
      spec
    ),
    "the post-reconnect live frame must follow the replayed frame"
  )
  assert.ok(
    /receives the next live message/u.test(spec),
    "the test must verify delivery resumes after reconnection"
  )
  assert.match(spec, /deleteOwnMessage/u)
  assert.match(spec, /trace:\s*["']off["']/u)
  assert.match(spec, /screenshot:\s*["']off["']/u)
  assert.doesNotMatch(spec, /routeWebSocket|WebSocket\s*=\s*new\s+Mock/u)
})
