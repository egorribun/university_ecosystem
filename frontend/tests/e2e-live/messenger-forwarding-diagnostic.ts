import type { Page, TestInfo } from "@playwright/test"

// The existing outer prefix is a legacy transport-evidence label, not a claim
// that this initial room observation is a reconnect. Schema/scenario identify it.
const PREFIX = "UE_LIVE_RECONNECT_V1 "
const KEYS = [
  "schema",
  "scenario",
  "project",
  "attempt",
  "sockets",
  "joinSentSockets",
  "openJoinSentSockets",
  "sourceFrames",
  "sourceFramesAfterJoinSent",
  "sourceAccepted",
  "socketsCapped",
  "framesCapped",
]
const COUNTS = [
  "sockets",
  "joinSentSockets",
  "openJoinSentSockets",
  "sourceFrames",
  "sourceFramesAfterJoinSent",
]
const FLAGS = ["sourceAccepted", "socketsCapped", "framesCapped"]

export function serializeForwardingDiagnostic(value: unknown): string | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null
  const record = value as Record<string, unknown>
  if (Object.keys(record).length !== KEYS.length || KEYS.some((key) => !Object.hasOwn(record, key)))
    return null
  if (record.schema !== 2 || record.scenario !== "forwarding-source-receive") return null
  if (typeof record.project !== "string" || !["desktop", "mobile"].includes(record.project))
    return null
  if (record.attempt !== 0 && record.attempt !== 1) return null
  if (
    COUNTS.some(
      (key) =>
        typeof record[key] !== "number" ||
        !Number.isInteger(record[key]) ||
        Number(record[key]) < 0 ||
        Number(record[key]) > 32
    )
  )
    return null
  if (FLAGS.some((key) => typeof record[key] !== "boolean")) return null
  if (
    Number(record.openJoinSentSockets) > Number(record.joinSentSockets) ||
    Number(record.joinSentSockets) > Number(record.sockets) ||
    Number(record.sourceFramesAfterJoinSent) > Number(record.sourceFrames)
  )
    return null
  return PREFIX + JSON.stringify(Object.fromEntries(KEYS.map((key) => [key, record[key]]))) + "\n"
}

export type ForwardingSourceDiagnostic = {
  report: (sourceAccepted: boolean) => void
}

export function observeForwardingSource(
  page: Page,
  room: string,
  source: string,
  info: Pick<TestInfo, "project" | "retry">,
  write: (line: string) => void = (line) => process.stdout.write(line)
): ForwardingSourceDiagnostic {
  const sessions: Array<{ joined: boolean; closed: boolean }> = []
  let socketsCapped = false
  let framesCapped = false
  let sourceFrames = 0
  let sourceFramesAfterJoinSent = 0
  let reported = false
  const visit = (raw: unknown, accept: (frame: Record<string, unknown>) => void) => {
    const pending = [raw]
    let visited = 0
    while (pending.length && visited++ < 128) {
      const value = pending.pop()
      if (!value || typeof value !== "object") continue
      if (Array.isArray(value)) pending.push(...value.slice(0, 128))
      else {
        const frame = value as Record<string, unknown>
        accept(frame)
        pending.push(...Object.values(frame).slice(0, 128))
      }
    }
    if (pending.length) framesCapped = true
  }
  const parse = (payload: string | Buffer, accept: (frame: Record<string, unknown>) => void) => {
    if (payload.length > 65_536) {
      framesCapped = true
      return
    }
    try {
      visit(JSON.parse(payload.toString()) as unknown, accept)
    } catch {
      /* No payload/error text is retained. */
    }
  }
  page.on("websocket", (socket) => {
    if (sessions.length === 32) {
      socketsCapped = true
      return
    }
    const session = { joined: false, closed: false }
    sessions.push(session)
    socket.on("close", () => {
      session.closed = true
    })
    socket.on("framesent", ({ payload }) =>
      parse(payload, (frame) => {
        if (frame.type === "join" && frame.room === room) session.joined = true
      })
    )
    socket.on("framereceived", ({ payload }) =>
      parse(payload, (frame) => {
        if (
          frame.type !== "new_message" ||
          frame.chat_id !== room ||
          !frame.message ||
          typeof frame.message !== "object"
        )
          return
        const message = frame.message as Record<string, unknown>
        if (message.content !== source || message.forwarded_from_name) return
        if (sourceFrames === 32) {
          framesCapped = true
          return
        }
        sourceFrames++
        if (session.joined) sourceFramesAfterJoinSent++
      })
    )
  })
  return {
    report(sourceAccepted) {
      if (reported) return
      reported = true
      const line = serializeForwardingDiagnostic({
        schema: 2,
        scenario: "forwarding-source-receive",
        project: info.project.name,
        attempt: info.retry,
        sockets: sessions.length,
        joinSentSockets: sessions.filter((s) => s.joined).length,
        openJoinSentSockets: sessions.filter((s) => s.joined && !s.closed).length,
        sourceFrames,
        sourceFramesAfterJoinSent,
        sourceAccepted,
        socketsCapped,
        framesCapped,
      })
      // Evidence must never replace the scenario's original failure or cleanup.
      if (line) {
        try {
          write(line)
        } catch {
          /* Diagnostic output is best effort. */
        }
      }
    },
  }
}
