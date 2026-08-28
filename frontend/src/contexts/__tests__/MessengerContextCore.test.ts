import { describe, expect, it } from "vitest"

import { getUnreadChatCount } from "../MessengerContextCore"

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
})
