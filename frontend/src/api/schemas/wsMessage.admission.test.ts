import { describe, expect, it } from "vitest"
import { parseWsMessage } from "./wsMessage"

const room = "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA"
const nonce = "a1".repeat(16)

describe("room admission control", () => {
  it("accepts a flat room admission preserving the exact room and nonce", () => {
    expect(parseWsMessage(JSON.stringify({ type: "room_admitted", room, nonce }))).toEqual({
      type: "room_admitted",
      room,
      nonce,
    })
  })

  it.each([
    { type: "room_admitted", room, nonce: "short" },
    { type: "room_admitted", room: "bad", nonce },
    { type: "room_admitted", room, nonce: nonce.toUpperCase() },
    { type: "forwarded", payload: { type: "room_admitted", room, nonce } },
    { type: "room_admitted", room, nonce, payload: { type: "room_admitted", room, nonce } },
    { type: "room_admitted", room, nonce, replayed: true },
  ])("rejects malformed or enveloped admission %#", (frame) => {
    expect(parseWsMessage(JSON.stringify(frame))).toBeNull()
  })
})

it.each([{ seq: 1 }, { resume_token: "synthetic-cursor" }, { payload: null }])(
  "rejects direct ACK with replay metadata or a payload %#",
  (extra) => {
    expect(
      parseWsMessage(JSON.stringify({ type: "room_admitted", room, nonce, ...extra }))
    ).toBeNull()
  }
)
