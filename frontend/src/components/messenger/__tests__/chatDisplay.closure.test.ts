import { describe, expect, it, vi } from "vitest"
import type { Chat } from "@/api/chat"
import { chatDisplayInfo } from "@/components/messenger/chatDisplay"

describe("chatDisplayInfo defensive identity", () => {
  it("uses the translated group name when the stored name is blank", () => {
    const t = vi.fn(() => "Untitled group")
    const chat = {
      chat_type: "group",
      name: "   ",
      participants: [],
    } as unknown as Chat

    expect(chatDisplayInfo(chat, "me", t as never)).toMatchObject({
      name: "Untitled group",
      isGroup: true,
      memberCount: 0,
    })
    expect(t).toHaveBeenCalledWith("messenger:group.untitled")
  })

  it("resolves the other DM participant, preserving avatar and participant count", () => {
    const t = vi.fn(() => "Unknown user")
    const other = {
      id: "peer",
      full_name: "Peer",
      avatar_url: "/peer.png",
    }
    const chat = {
      chat_type: "direct",
      name: null,
      participants: [{ id: "me", full_name: "Me", avatar_url: null }, other],
    } as unknown as Chat

    expect(chatDisplayInfo(chat, "me", t as never)).toEqual({
      name: "Peer",
      avatar: "/peer.png",
      isGroup: false,
      memberCount: 2,
      otherParticipant: other,
    })
    expect(t).not.toHaveBeenCalled()
  })

  it("uses defensive fallbacks when a DM has no counterpart or avatar", () => {
    const t = vi.fn(() => "Unknown user")
    const chat = {
      chat_type: "direct",
      name: null,
      participants: [{ id: "me", full_name: "", avatar_url: null }],
    } as unknown as Chat

    expect(chatDisplayInfo(chat, "me", t as never)).toMatchObject({
      name: "Unknown user",
      avatar: "",
      isGroup: false,
      memberCount: 1,
      otherParticipant: undefined,
    })
    expect(t).toHaveBeenCalledWith("messenger:unknownUser")
  })

  it("keeps a DM's explicit empty name fallback while retaining its avatar", () => {
    const t = vi.fn(() => "Unknown user")
    const chat = {
      chat_type: "direct",
      name: null,
      participants: [{ id: "peer", full_name: "", avatar_url: "/peer.png" }],
    } as unknown as Chat

    expect(chatDisplayInfo(chat, "me", t as never)).toMatchObject({
      name: "Unknown user",
      avatar: "/peer.png",
      isGroup: false,
      otherParticipant: expect.objectContaining({ id: "peer" }),
    })
  })

  it("uses the translated fallback when a group name is null", () => {
    const t = vi.fn(() => "Untitled group")
    const chat = {
      chat_type: "group",
      name: null,
      participants: [],
    } as unknown as Chat

    expect(() => chatDisplayInfo(chat, "me", t as never)).not.toThrow()
    expect(chatDisplayInfo(chat, "me", t as never)).toMatchObject({
      name: "Untitled group",
      avatar: "",
      isGroup: true,
      memberCount: 0,
    })
    expect(t).toHaveBeenCalledWith("messenger:group.untitled")
  })
})
