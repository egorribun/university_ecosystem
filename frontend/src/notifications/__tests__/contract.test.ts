import { describe, expect, it } from "vitest"

import {
  CANONICAL_NOTIFICATION_TOPICS,
  normalizeNotificationTopic,
  resolveNotificationAppPath,
  resolveNotificationDeepLink,
  resolveOptionalSameOriginUrl,
} from "../contract"

describe("canonical notification contract", () => {
  it("exposes the five canonical topics in product order", () => {
    expect(CANONICAL_NOTIFICATION_TOPICS).toEqual([
      "news.published",
      "schedule.changed",
      "events.published",
      "chat.message.created",
      "system.release",
    ])
  })

  it.each([
    ["news", "news.published"],
    ["schedule", "schedule.changed"],
    ["events", "events.published"],
    ["chat", "chat.message.created"],
    ["system", "system.release"],
    [" NEWS.PUBLISHED ", "news.published"],
  ])("migrates %s to %s", (raw, expected) => {
    expect(normalizeNotificationTopic(raw)).toBe(expected)
  })

  it("rejects unknown topics", () => {
    expect(normalizeNotificationTopic("unknown")).toBeNull()
  })

  it("allows only same-origin http(s) deep links", () => {
    expect(resolveNotificationDeepLink("/events/42", "https://campus.example")).toBe(
      "https://campus.example/events/42"
    )
    expect(
      resolveNotificationDeepLink("https://evil.example/phish", "https://campus.example")
    ).toBe("https://campus.example/")
    expect(resolveNotificationDeepLink("javascript:alert(1)", "https://campus.example")).toBe(
      "https://campus.example/"
    )
  })

  it("drops invalid or cross-origin reporting endpoints", () => {
    expect(resolveOptionalSameOriginUrl("/api/report", "https://campus.example")).toBe(
      "https://campus.example/api/report"
    )
    expect(
      resolveOptionalSameOriginUrl("https://evil.example/collect", "https://campus.example")
    ).toBeNull()
    expect(resolveOptionalSameOriginUrl("javascript:alert(1)", "https://campus.example")).toBeNull()
  })

  it("returns only safe app-relative paths for notification center links", () => {
    expect(resolveNotificationAppPath("/news/42?from=push#comments")).toBe(
      "/news/42?from=push#comments"
    )
    expect(resolveNotificationAppPath("https://evil.example/phish")).toBeUndefined()
    expect(resolveNotificationAppPath("//evil.example/phish")).toBeUndefined()
  })
})
