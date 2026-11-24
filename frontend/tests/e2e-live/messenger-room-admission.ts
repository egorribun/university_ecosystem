type RecordValue = Record<string, unknown>
type Attempt = { room: string; nonce: string }

const isRecord = (value: unknown): value is RecordValue =>
  typeof value === "object" && value !== null && !Array.isArray(value)

/** One instance per observed physical socket. No absence of ACK implies admission. */
export function createRoomAdmissionObserver() {
  let current: Attempt | null = null
  let admitted: Attempt | null = null
  const seen = new Set<string>()
  return {
    sent(frame: unknown) {
      if (!isRecord(frame)) return
      if (frame.type === "join") {
        current = null
        admitted = null
        if (
          typeof frame.room === "string" &&
          isRecord(frame.payload) &&
          typeof frame.payload.admission_nonce === "string" &&
          /^[0-9a-f]{32}$/.test(frame.payload.admission_nonce) &&
          !seen.has(frame.payload.admission_nonce)
        ) {
          seen.add(frame.payload.admission_nonce)
          current = { room: frame.room, nonce: frame.payload.admission_nonce }
        }
      } else if (frame.type === "leave" && frame.room === current?.room) {
        current = null
        admitted = null
      }
    },
    received(frame: unknown) {
      if (!isRecord(frame)) return
      if (frame.type === "rate_limit_exceeded" || frame.type === "error") {
        current = null
        admitted = null
        return
      }
      if (
        frame.type === "room_admitted" &&
        !("payload" in frame) &&
        !("seq" in frame) &&
        !("replayed" in frame) &&
        !("resume_token" in frame) &&
        current !== null &&
        frame.room === current.room &&
        frame.nonce === current.nonce
      )
        admitted = current
    },
    snapshot(room: string) {
      return current !== null && admitted === current && current.room === room ? current : null
    },
    isCurrent(attempt: Attempt) {
      return current === attempt && admitted === attempt
    },
  }
}
