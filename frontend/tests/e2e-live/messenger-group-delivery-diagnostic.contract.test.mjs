import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import { URL } from "node:url"
import * as diagnostic from "./messenger-group-delivery-diagnostic.ts"
const { reportGroupDeliveryFailure } = diagnostic

const room = "room-private-marker"
const id = "message-private-marker"
const body = "content-private-marker"
const beforeSend = { owner: true, teacher: false, secondMember: null }
const session = (joined, closed, events = []) => ({
  roomJoins: joined ? [room] : [],
  closed: () => closed,
  heartbeat: { acknowledged: () => false },
  groupEvents: events,
})
const event = (messageId, content) => ({ type: "new_message", chatId: room, messageId, content })
const observers = {
  owner: { sessions: [session(true, false, [event(id, body)])] },
  teacher: { sessions: [session(true, true, [event(id, "different")])] },
  secondMember: { sessions: [session(true, false)] },
}

test("R23 diagnostic projects three observers without private values", () => {
  const lines = []
  reportGroupDeliveryFailure(
    observers,
    room,
    id,
    body,
    beforeSend,
    { project: { name: "desktop" }, retry: 0 },
    (line) => lines.push(line)
  )
  assert.equal(lines.length, 1)
  assert.match(lines[0], /^UE_LIVE_RECONNECT_V1 /u)
  for (const value of [room, id, body, "different"]) assert.equal(lines[0].includes(value), false)
  const record = JSON.parse(lines[0].slice("UE_LIVE_RECONNECT_V1 ".length))
  assert.equal(record.scenario, "group-initial-delivery")
  assert.equal(record.owner.matchingFrames, 1)
  assert.equal(record.teacher.targetFrames, 1)
  assert.equal(record.teacher.matchingFrames, 0)
  assert.equal(record.teacher.openJoinSentSockets, 0)
  assert.equal(record.teacher.pongAfterJoinSentSockets, 0)
  assert.equal(record.owner.pongBeforeSend, true)
  assert.equal(record.secondMember.pongBeforeSend, null)
  assert.equal(record.secondMember.targetFrames, 0)
})

test("R23 diagnostic is bounded, fail-closed and best effort", () => {
  const many = {
    sessions: Array.from({ length: 33 }, () =>
      session(
        true,
        false,
        Array.from({ length: 33 }, () => event(id, body))
      )
    ),
  }
  const lines = []
  reportGroupDeliveryFailure(
    { owner: many, teacher: many, secondMember: many },
    room,
    id,
    body,
    beforeSend,
    { project: { name: "mobile" }, retry: 1 },
    (line) => lines.push(line)
  )
  assert.equal(lines.length, 1)
  const record = JSON.parse(lines[0].slice("UE_LIVE_RECONNECT_V1 ".length))
  assert.equal(record.owner.sockets, 32)
  assert.equal(record.owner.targetFrames, 32)
  assert.equal(record.owner.socketsCapped, true)
  assert.equal(record.owner.framesCapped, true)
  reportGroupDeliveryFailure(
    observers,
    room,
    id,
    body,
    beforeSend,
    { project: { name: "unsafe" }, retry: 0 },
    (line) => lines.push(line)
  )
  reportGroupDeliveryFailure(
    observers,
    room,
    id,
    body,
    beforeSend,
    { project: { name: "desktop" }, retry: 9 },
    (line) => lines.push(line)
  )
  assert.equal(lines.length, 1)
  assert.doesNotThrow(() =>
    reportGroupDeliveryFailure(
      observers,
      room,
      id,
      body,
      beforeSend,
      { project: { name: "desktop" }, retry: 0 },
      () => {
        throw Error("sink")
      }
    )
  )
})

test("R23 heartbeat observation requires a matching pong after the join was sent", () => {
  assert.equal(typeof diagnostic.createGroupHeartbeatObservation, "function")
  const heartbeat = diagnostic.createGroupHeartbeatObservation()
  const nonce = "a".repeat(32)
  heartbeat.sent({ type: "heartbeat_ping", nonce }, [])
  heartbeat.received({ type: "heartbeat_pong", nonce })
  assert.equal(heartbeat.acknowledged(room), false)
  heartbeat.sent({ type: "heartbeat_ping", nonce }, [room])
  heartbeat.received({ type: "heartbeat_pong", nonce: "b".repeat(32) })
  assert.equal(heartbeat.acknowledged(room), false)
  heartbeat.received({ type: "heartbeat_pong", nonce })
  assert.equal(heartbeat.acknowledged(room), true)
  const lines = []
  const attended = { sessions: [{ ...session(true, false), heartbeat }] }
  reportGroupDeliveryFailure(
    { owner: attended, teacher: attended, secondMember: attended },
    room,
    id,
    body,
    beforeSend,
    { project: { name: "desktop" }, retry: 0 },
    (line) => lines.push(line)
  )
  const record = JSON.parse(lines[0].slice("UE_LIVE_RECONNECT_V1 ".length))
  assert.equal(record.teacher.pongAfterJoinSentSockets, 1)
  assert.equal(lines[0].includes(nonce), false)
})

test("R23 diagnostic runs only when the initial delivery assertion fails", async () => {
  const source = await readFile(
    new URL("./messenger-group-isolation.live.spec.ts", import.meta.url),
    "utf8"
  )
  const start = source.indexOf("const sentMessage =")
  const end = source.indexOf("await expect(teacherLog.getByText", start)
  assert.ok(start >= 0 && end > start)
  const initial = source.slice(start, end)
  assert.equal((initial.match(/reportGroupDeliveryFailure\(/gu) ?? []).length, 1)
  assert.match(
    initial,
    /try \{[\s\S]*?eventsForMessage\(socket, chatId, sentMessage\.id\)[\s\S]*?\.toBe\(true\)[\s\S]*?\} catch \(error\) \{[\s\S]*?reportGroupDeliveryFailure\([\s\S]*?throw error\s*\}/u
  )
})

test("R23 readiness snapshots a pong on an open joined socket before sending", () => {
  assert.equal(typeof diagnostic.groupPongBeforeSend, "function")
  const heartbeat = diagnostic.createGroupHeartbeatObservation()
  const nonce = "c".repeat(32)
  heartbeat.sent({ type: "heartbeat_ping", nonce }, [room])
  heartbeat.received({ type: "heartbeat_pong", nonce })
  const observed = { sessions: [{ ...session(true, false), heartbeat }] }
  const result = diagnostic.groupPongBeforeSend(
    { owner: observed, teacher: observed, secondMember: { sessions: [session(true, true)] } },
    room
  )
  assert.deepEqual(result, { owner: true, teacher: true, secondMember: false })
  const failed = {
    sessions: [
      {
        ...session(true, false),
        closed: () => {
          throw Error("unavailable")
        },
        heartbeat,
      },
    ],
  }
  assert.equal(
    diagnostic.groupPongBeforeSend(
      { owner: failed, teacher: observed, secondMember: observed },
      room
    ).owner,
    null
  )
})
