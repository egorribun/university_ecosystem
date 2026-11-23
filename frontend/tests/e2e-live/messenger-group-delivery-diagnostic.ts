type GroupEvent = {
  type: string
  chatId: string
  messageId: string
  content?: string
}
type Session = {
  roomJoins: string[]
  groupEvents: GroupEvent[]
  closed: () => boolean
  heartbeat: { acknowledged: (room: string) => boolean }
}
type Observation = { sessions: Session[] }
type Observers = { owner: Observation; teacher: Observation; secondMember: Observation }
type TestIdentity = { project: { name: string }; retry: number }
type BeforeSend = { owner: boolean | null; teacher: boolean | null; secondMember: boolean | null }

export function createGroupHeartbeatObservation() {
  let pending: { nonce: string; rooms: string[] } | null = null
  let acknowledgedRooms: string[] = []
  return {
    sent(value: unknown, roomJoins: string[]): void {
      if (!value || typeof value !== "object" || Array.isArray(value)) return
      const frame = value as Record<string, unknown>
      if (
        frame.type !== "heartbeat_ping" ||
        typeof frame.nonce !== "string" ||
        !/^[0-9a-f]{32}$/u.test(frame.nonce)
      )
        return
      pending = { nonce: frame.nonce, rooms: roomJoins.slice(-32) }
    },
    received(value: unknown): void {
      if (!value || typeof value !== "object" || Array.isArray(value)) return
      const frame = value as Record<string, unknown>
      if (frame.type !== "heartbeat_pong" || !pending || frame.nonce !== pending.nonce) return
      acknowledgedRooms = Array.from(new Set([...acknowledgedRooms, ...pending.rooms])).slice(-32)
      pending = null
    },
    acknowledged(room: string): boolean {
      return acknowledgedRooms.includes(room)
    },
  }
}

export function groupPongBeforeSend(observers: Observers, room: string): BeforeSend {
  const read = (observation: Observation): boolean | null => {
    try {
      return observation.sessions
        .slice(-32)
        .some(
          (session) =>
            !session.closed() &&
            session.roomJoins.includes(room) &&
            session.heartbeat.acknowledged(room)
        )
    } catch {
      return null
    }
  }
  return {
    owner: read(observers.owner),
    teacher: read(observers.teacher),
    secondMember: read(observers.secondMember),
  }
}

function project(
  observation: Observation,
  room: string,
  messageId: string,
  content: string,
  pongBeforeSend: boolean | null
) {
  const recent = observation.sessions.slice(-32)
  let closedSockets = 0
  let joinSentSockets = 0
  let openJoinSentSockets = 0
  let pongAfterJoinSentSockets = 0
  let targetFrames = 0
  let matchingFrames = 0
  let framesCapped = false
  for (const session of recent) {
    const closed = session.closed()
    const joined = session.roomJoins.includes(room)
    if (closed) closedSockets++
    if (joined) joinSentSockets++
    if (joined && !closed) openJoinSentSockets++
    if (session.heartbeat.acknowledged(room)) pongAfterJoinSentSockets++
    if (framesCapped) continue
    for (const event of session.groupEvents) {
      if (event.type !== "new_message" || event.chatId !== room || event.messageId !== messageId)
        continue
      if (targetFrames === 32) {
        framesCapped = true
        break
      }
      targetFrames++
      if (event.content === content) matchingFrames++
    }
  }
  return {
    sockets: recent.length,
    closedSockets,
    joinSentSockets,
    openJoinSentSockets,
    pongAfterJoinSentSockets,
    targetFrames,
    matchingFrames,
    socketsCapped: observation.sessions.length > recent.length,
    framesCapped,
    pongBeforeSend: typeof pongBeforeSend === "boolean" ? pongBeforeSend : null,
  }
}

// Failure-only, counts and booleans only; message and room values stay in memory.
export function reportGroupDeliveryFailure(
  observers: Observers,
  room: string,
  messageId: string,
  content: string,
  beforeSend: BeforeSend,
  info: TestIdentity,
  write: (line: string) => void = (line) => process.stdout.write(line)
): void {
  try {
    if (!["desktop", "mobile"].includes(info.project.name) || ![0, 1].includes(info.retry)) return
    const record = {
      schema: 4,
      scenario: "group-initial-delivery",
      project: info.project.name,
      attempt: info.retry,
      owner: project(observers.owner, room, messageId, content, beforeSend.owner),
      teacher: project(observers.teacher, room, messageId, content, beforeSend.teacher),
      secondMember: project(
        observers.secondMember,
        room,
        messageId,
        content,
        beforeSend.secondMember
      ),
    }
    write(`UE_LIVE_RECONNECT_V1 ${JSON.stringify(record)}\n`)
  } catch {
    // Diagnostics must never replace the original assertion or affect cleanup.
  }
}
