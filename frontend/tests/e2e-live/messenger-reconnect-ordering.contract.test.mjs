import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import { URL } from "node:url"

const specUrl = new URL("./messenger-reconnect-ordering.live.spec.ts", import.meta.url)
const configUrl = new URL("../../playwright.live.config.ts", import.meta.url)

test("live direct-message reconnect proves ordered, exactly-once replay for unique users", async () => {
  let spec
  try {
    spec = await readFile(specUrl, "utf8")
  } catch {
    assert.fail("a dedicated live direct-message reconnect-ordering scenario must exist")
  }

  const config = await readFile(configUrl, "utf8")
  const requireMatch = (pattern, message, source = spec) => assert.ok(pattern.test(source), message)

  requireMatch(/testDir:\s*["']\.\/tests\/e2e-live["']/u, "the live config owns this spec", config)
  requireMatch(/testMatch:\s*\/\.\*\\\.live\\\.spec\\\.ts\$\//u, "the spec is discoverable", config)
  requireMatch(
    /test\.use\(\{\s*trace:\s*["']off["'],\s*screenshot:\s*["']off["']/u,
    "live chat payloads and login requests are excluded from traces"
  )
  requireMatch(/randomUUID\(\)/u, "each run uses a fresh identity")
  requireMatch(/live-messenger-reconnect-sender-/u, "sender identity is unique per run")
  requireMatch(/live-messenger-reconnect-receiver-/u, "receiver identity is unique per run")
  requireMatch(/stubBreachedPasswordLookup/u, "password checks stay inside the test")
  requireMatch(/pathname\.endsWith\(["']\/auth\/register["']\)/u, "users register in the live app")
  requireMatch(/\/api\/v1\/users\/me/u, "both logged-in identities are confirmed")
  requireMatch(
    /new Set\(\[sender\.id, receiver\.id\]\)\.size\)\.toBe\(2\)/u,
    "sender and receiver are distinct generated users"
  )

  requireMatch(/newContext\(/u, "the receiver has an isolated browser context")
  requireMatch(/page\.on\(["']websocket["']/u, "the scenario observes the real WebSocket")
  requireMatch(/socket\.on\(["']framesent["']/u, "room joins are observed on the socket")
  requireMatch(/socket\.on\(["']framereceived["']/u, "message frames are observed on the socket")
  requireMatch(/setOffline\(true\)/u, "the real receiver transport is disconnected")
  requireMatch(/setOffline\(false\)/u, "the receiver transport is reconnected")
  requireMatch(/navigator\.onLine/u, "the browser confirms its offline state")
  requireMatch(/\/api\/v1\/chats\/\$\{chatId\}\/messages/u, "DM messages use the live API")

  requireMatch(
    /const offlineMessages = \[[\s\S]*?sendLiveMessage\([\s\S]*?offlineMessageIds/u,
    "multiple distinct messages are sent only after the receiver disconnects"
  )
  requireMatch(
    /replayedFrames\.map\(\(message\) => message\.id\)\)\.toEqual\(offlineMessageIds\)/u,
    "the missed messages must be replayed in their send order"
  )
  requireMatch(
    /new Set\(replayedFrames\.map\(\(message\) => message\.id\)\)\.size\)\.toBe\(offlineMessageIds\.length\)/u,
    "the replay set must contain no duplicate ids"
  )
  requireMatch(
    /replayedFrames\.every\(\(message\) => message\.replayed\)\)\.toBe\(true\)/u,
    "the observed WebSocket frames must be marked as replayed"
  )
  requireMatch(
    /baselineSequence\)\.toBeLessThan\(replaySequences\[0\]!\)/u,
    "replay follows the baseline"
  )
  requireMatch(
    /replaySequences\[0\]!\)\.toBeLessThan\(replaySequences\[1\]!\)/u,
    "replay sequence is ordered"
  )
  requireMatch(
    /allTestDeliveries\.map\(\(message\) => message\.id\)\)\.toEqual\(expectedMessageIds\)/u,
    "baseline, replay, and post-reconnect frames are observed in send order"
  )
  requireMatch(
    /allTestDeliveries\)\.toHaveLength\(expectedMessageIds\.length\)/u,
    "baseline, replay, and post-reconnect frames have no duplicates or omissions"
  )
  requireMatch(
    /receiverLog\.getByText\(message\.content,\s*\{\s*exact:\s*true\s*\}\)\)\.toHaveCount\(1\)/u,
    "each replayed message appears once in the receiver UI"
  )

  requireMatch(/deleteOwnedLiveMessage\(/u, "messages are removed through sender-owned UI actions")
  requireMatch(/deleteOnlyCreatedChat\(/u, "cleanup deletes only the generated direct chat")
  requireMatch(/deleteOnlyCreatedAccount\(/u, "cleanup deletes only generated accounts")
  requireMatch(/X-CSRF-Token/u, "administrative cleanup is CSRF protected")
  assert.doesNotMatch(spec, /useMockApi|page\.route\(|routeWebSocket\(|fulfill\(/u)
})
