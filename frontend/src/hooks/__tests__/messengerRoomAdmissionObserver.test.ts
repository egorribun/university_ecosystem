import { describe, expect, it } from "vitest"
import { createRoomAdmissionObserver } from "../../../tests/e2e-live/messenger-room-admission"

const room = "a-room"
const nonce = "a".repeat(32)
const join = { type: "join", room, payload: { admission_nonce: nonce } }
const admitted = { type: "room_admitted", room, nonce }

describe("live admission observer", () => {
  it("requires a matching flat acknowledgement on the same observer", () => {
    const first = createRoomAdmissionObserver()
    const second = createRoomAdmissionObserver()
    first.sent(join)
    expect(first.snapshot(room)).toBeNull()
    second.received(admitted)
    expect(second.snapshot(room)).toBeNull()
    first.received({ type: "heartbeat_pong", nonce })
    first.received({ type: "forwarded", payload: admitted })
    first.received({ ...admitted, payload: admitted })
    first.received({ ...admitted, replayed: true })
    first.received({ ...admitted, room: "other" })
    first.received({ ...admitted, nonce: "b".repeat(32) })
    expect(first.snapshot(room)).toBeNull()
    first.received(admitted)
    expect(first.snapshot(room)).not.toBeNull()
    expect(first.snapshot("other")).toBeNull()
  })

  it("invalidates the receipt on rejoin, leave, denial, or a legacy join", () => {
    for (const retire of [
      (observer: ReturnType<typeof createRoomAdmissionObserver>) => observer.sent(join),
      (observer: ReturnType<typeof createRoomAdmissionObserver>) =>
        observer.sent({ type: "leave", room }),
      (observer: ReturnType<typeof createRoomAdmissionObserver>) =>
        observer.sent({ type: "join", room }),
      (observer: ReturnType<typeof createRoomAdmissionObserver>) =>
        observer.received({ type: "rate_limit_exceeded" }),
      (observer: ReturnType<typeof createRoomAdmissionObserver>) =>
        observer.received({ type: "error" }),
    ]) {
      const observer = createRoomAdmissionObserver()
      observer.sent(join)
      observer.received(admitted)
      const receipt = observer.snapshot(room)!
      expect(observer.isCurrent(receipt)).toBe(true)
      retire(observer)
      expect(observer.isCurrent(receipt)).toBe(false)
      expect(observer.snapshot(room)).toBeNull()
    }
  })

  it("rejects stale same-room ACKs and malformed input", () => {
    const observer = createRoomAdmissionObserver()
    observer.sent(null)
    observer.received(null)
    observer.sent(join)
    observer.sent({ ...join, payload: { admission_nonce: "b".repeat(32) } })
    observer.received(admitted)
    expect(observer.snapshot(room)).toBeNull()
    observer.sent({ ...join, payload: { admission_nonce: "invalid" } })
    observer.received(admitted)
    expect(observer.snapshot(room)).toBeNull()
  })
})
