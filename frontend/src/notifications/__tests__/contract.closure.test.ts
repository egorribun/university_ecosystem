import { describe, expect, it } from "vitest"

import {
  normalizeNotificationTopic,
  normalizeNotificationTopics,
  resolveOptionalSameOriginUrl,
} from "../contract"

describe("notification contract closure", () => {
  it.each([null, 7, {}, "", "   "])("rejects a non-topic value without coercion", (value) => {
    expect(normalizeNotificationTopic(value)).toBeNull()
  })

  it("normalizes a mixed topic list in first-seen order without duplicates", () => {
    expect(
      normalizeNotificationTopics([
        " NEWS ",
        "news.published",
        "events",
        "unknown",
        null,
        "events.published",
        "system.release",
      ])
    ).toEqual(["news.published", "events.published", "system.release"])
  })

  it.each([undefined, null, "not a list", { topic: "news" }])(
    "treats a non-array topic collection as empty",
    (value) => {
      expect(normalizeNotificationTopics(value)).toEqual([])
    }
  )

  it("rejects non-string, blank, malformed and unsupported notification URLs", () => {
    const origin = "https://campus.example"

    expect(resolveOptionalSameOriginUrl(null, origin)).toBeNull()
    expect(resolveOptionalSameOriginUrl("   ", origin)).toBeNull()
    expect(resolveOptionalSameOriginUrl("http://[invalid", origin)).toBeNull()
    expect(resolveOptionalSameOriginUrl("ftp://campus.example/file", origin)).toBeNull()
  })
})
