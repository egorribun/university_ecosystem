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
})
