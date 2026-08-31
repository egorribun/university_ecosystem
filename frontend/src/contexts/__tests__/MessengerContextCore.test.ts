import { renderHook } from "@testing-library/react"
import { createElement } from "react"
import { describe, expect, it } from "vitest"

import {
  DEFAULT_MESSENGER_CONTEXT,
  MessengerContext,
  getUnreadChatCount,
  useMessenger,
} from "../MessengerContextCore"

describe("getUnreadChatCount", () => {
  it("sums only safe non-negative integer unread counts from a chat items array", () => {
    expect(
      getUnreadChatCount([
        { unread_count: 2 },
        { unread_count: 5.5 },
        { unread_count: -4 },
        { unread_count: Number.NaN },
        { unread_count: Number.POSITIVE_INFINITY },
        { unread_count: "3" },
        null,
        1,
      ])
    ).toBe(2)
  })

  it("fails closed when an optional chat response has no items array", () => {
    expect(getUnreadChatCount(undefined)).toBe(0)
    expect(getUnreadChatCount(null)).toBe(0)
    expect(getUnreadChatCount({})).toBe(0)
    expect(getUnreadChatCount({ items: [] })).toBe(0)
  })

  it("keeps the dependency-free default context safe to call", () => {
    expect(DEFAULT_MESSENGER_CONTEXT.unreadCount).toBe(0)
    expect(DEFAULT_MESSENGER_CONTEXT.isConnected).toBe(false)
    expect(DEFAULT_MESSENGER_CONTEXT.presenceMap).toEqual({})
    expect(DEFAULT_MESSENGER_CONTEXT.getTypingUsersForChat("chat-1")).toEqual([])

    // The shell can mount before the lazy messenger route. Every fallback
    // action is intentionally a no-op rather than a throw in that window.
    expect(() => {
      DEFAULT_MESSENGER_CONTEXT.sendTyping("chat-1")
      DEFAULT_MESSENGER_CONTEXT.sendJoin("chat-1")
      DEFAULT_MESSENGER_CONTEXT.sendLeave("chat-1")
    }).not.toThrow()
  })

  it("reads a provided context value through useMessenger", () => {
    const value = { ...DEFAULT_MESSENGER_CONTEXT, unreadCount: 3 }
    const { result } = renderHook(() => useMessenger(), {
      wrapper: ({ children }) => createElement(MessengerContext.Provider, { value }, children),
    })

    expect(result.current).toBe(value)
  })

  it("fails loudly when useMessenger is called outside a provider", () => {
    expect(() => renderHook(() => useMessenger())).toThrow(
      "useMessenger must be used within MessengerProvider"
    )
  })
})
