type ReadFrame = { chatId: string; userId: string }
type Session = {
  closed(): boolean
  roomJoins: string[]
  readFrames: ReadFrame[]
}
type TestIdentity = { project: { name: string }; retry: number }

// Use the shared transport channel with a distinct read-receipt scenario.
export function reportReadReceiptFailure(
  sessions: Session[],
  chatId: string,
  userId: string | null,
  test: TestIdentity,
  write: (line: string) => void = (line) => process.stdout.write(line)
): void {
  try {
    if (!["desktop", "mobile"].includes(test.project.name) || ![0, 1].includes(test.retry)) return
    // When capped, socket and frame counts describe the most recent 32 sessions.
    const recent = sessions.slice(-32)
    const unclosed = recent.filter((session) => !session.closed())
    const latest = unclosed.at(-1)
    let chatFrames = 0
    let matchingFrames = 0
    let framesCapped = false
    for (const session of recent) {
      for (const frame of session.readFrames) {
        if (frame.chatId !== chatId) continue
        if (chatFrames === 32) {
          framesCapped = true
          break
        }
        chatFrames++
        if (frame.userId === userId) matchingFrames++
      }
      if (framesCapped) break
    }
    const record = {
      schema: 3,
      scenario: "read-receipt-peer",
      project: test.project.name,
      attempt: test.retry,
      sockets: recent.length,
      closedSockets: recent.length - unclosed.length,
      latestUnclosedJoinSent: latest?.roomJoins.includes(chatId) ?? false,
      chatFrames,
      matchingFrames,
      socketsCapped: sessions.length > recent.length,
      framesCapped,
    }
    write(`UE_LIVE_RECONNECT_V1 ${JSON.stringify(record)}\n`)
  } catch {
    // Reporting must never replace the assertion failure or interfere with cleanup.
  }
}
