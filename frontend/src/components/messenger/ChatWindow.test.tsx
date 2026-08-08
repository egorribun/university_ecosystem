import { afterEach, describe, expect, it } from "vitest"
import { cleanup, render, screen } from "@testing-library/react"
import { axe } from "jest-axe"

import { ChatWindow } from "./ChatWindow"
import type { Message } from "./types"

/**
 * ChatWindow ARIA + axe tests.
 *
 * The chat container exposes role="log" + aria-live="polite" so screen
 * readers announce new messages without interrupting the user. The
 * scroller is virtualised via @tanstack/react-virtual; with no
 * messages the empty container must still be valid (no orphan
 * aria-label / no missing landmarks).
 */

const MSG_FIXTURE: Message[] = [
  {
    id: "1",
    senderId: "u-other",
    senderName: "Alice",
    senderAvatar: "",
    text: "Hello!",
    timestamp: "12:00",
    isMe: false,
  },
  {
    id: "2",
    senderId: "u-me",
    senderName: "Me",
    senderAvatar: "",
    text: "Hi there.",
    timestamp: "12:01",
    isMe: true,
    status: "read",
    // Wave 203 SW6 — the last read sent message renders the "Seen · HH:MM"
    // marker; included here so the axe pass covers the new render path.
    readAt: "2026-05-30T12:01:00+00:00",
    readAtLabel: "12:01",
    isLastRead: true,
  },
]

afterEach(() => {
  cleanup()
})

describe("ChatWindow — ARIA shape", () => {
  it("exposes role=log with aria-live=polite", () => {
    render(<ChatWindow messages={[]} />)
    const region = screen.getByRole("log")
    expect(region).toHaveAttribute("aria-live", "polite")
  })

  it("supplies a stable aria-label so screen readers identify the region", () => {
    render(<ChatWindow messages={[]} />)
    expect(screen.getByRole("log")).toHaveAttribute("aria-label", expect.any(String))
    // The label must be non-empty.
    expect(screen.getByRole("log").getAttribute("aria-label")?.length).toBeGreaterThan(0)
  })
})

describe("ChatWindow — accessibility", () => {
  it("has no axe violations when empty", async () => {
    const { container } = render(<ChatWindow messages={[]} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it("has no axe violations with messages", async () => {
    const { container } = render(<ChatWindow messages={MSG_FIXTURE} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
