import { describe, expect, it } from "vitest"
import {
  DEFAULT_ICON,
  buildNotificationDetails,
  getDefaultNotificationBody,
  getDefaultNotificationTitle,
  parsePushEventData,
} from "../notification-helpers"
import type { NotificationActionPayload } from "../notification-helpers"

describe("parsePushEventData", () => {
  it("returns empty payload when data is missing", () => {
    expect(parsePushEventData(undefined)).toEqual({})
    expect(parsePushEventData(null)).toEqual({})
  })

  it("parses JSON payloads", () => {
    const payload = { title: "Hello", body: "World" }
    const data = {
      json: () => payload,
      text: () => JSON.stringify(payload),
    }
    expect(parsePushEventData(data)).toEqual(payload)
  })

  it("falls back to text body when JSON parsing fails", () => {
    const data = {
      json: () => {
        throw new Error("bad json")
      },
      text: () => "raw-body",
    }
    expect(parsePushEventData(data)).toEqual({ body: "raw-body" })
  })

  it("returns an empty payload for non-object JSON, empty text, or text failures", () => {
    expect(parsePushEventData({ json: () => "not-an-object", text: () => "ignored" })).toEqual({})
    expect(
      parsePushEventData({
        json: () => {
          throw new Error("bad")
        },
        text: () => "",
      })
    ).toEqual({})
    expect(
      parsePushEventData({
        json: () => {
          throw new Error("bad")
        },
        text: () => {
          throw new Error("also bad")
        },
      })
    ).toEqual({})
  })
})

describe("buildNotificationDetails", () => {
  it("applies defaults for title and icon", () => {
    const result = buildNotificationDetails({})
    expect(result.title).toBe(getDefaultNotificationTitle())
    expect(result.options.icon).toBe(DEFAULT_ICON)
    expect(result.options.badge).toBe(DEFAULT_ICON)
    expect(result.options.body).toBe(getDefaultNotificationBody())
    expect(result.data.url).toBe("/")
  })

  it("maps payload data and returns payload type", () => {
    const result = buildNotificationDetails({
      title: "Custom",
      body: "Message",
      icon: "/icon.png",
      badge: "/badge.png",
      tag: "tag-id",
      url: "/path",
      data: { foo: "bar", type: " system  " },
      vibrate: [100],
      timestamp: 123,
      renotify: true,
    })

    expect(result.title).toBe("Custom")
    expect(result.options.body).toBe("Message")
    expect(result.options.icon).toBe("/icon.png")
    expect(result.options.badge).toBe("/badge.png")
    expect(result.options.vibrate).toEqual([100])
    expect(result.options.timestamp).toBe(123)
    expect(result.options.renotify).toBe(true)
    expect(result.options.data).toMatchObject({ foo: "bar", type: " system  " })
    expect(result.payloadType).toBe("system")
    expect(result.data.url).toBe("/path")
  })

  it("normalizes actions and collects action URLs", () => {
    const result = buildNotificationDetails({
      actions: [
        { action: " open ", title: "Open", icon: "icon.svg", url: "/open" },
        { action: "", title: "", url: "" },
      ],
    })

    expect(result.options.actions).toEqual([{ action: "open", title: "Open", icon: "icon.svg" }])
    expect(result.data.actionUrls).toEqual({ open: "/open" })
  })

  it("uses Russian defaults and preserves optional payload flags", () => {
    const originalLanguage = navigator.language
    Object.defineProperty(navigator, "language", { configurable: true, value: "ru-RU" })
    try {
      expect(getDefaultNotificationTitle()).toBe("Новое уведомление")
      expect(getDefaultNotificationBody()).toBe("У вас есть новое уведомление.")

      const result = buildNotificationDetails({
        title: "  ",
        body: "  ",
        icon: "/icon.png",
        badge: "",
        url: "",
        data: null as unknown as Record<string, unknown>,
        renotify: false,
        timestamp: 0,
        actions: [{ action: "save", title: " Save " }],
      })

      expect(result.title).toBe("Новое уведомление")
      expect(result.options.body).toBe("У вас есть новое уведомление.")
      expect(result.options.icon).toBe("/icon.png")
      expect(result.options.badge).toBe("/icon.png")
      expect(result.options.renotify).toBe(false)
      expect(result.options.timestamp).toBe(0)
      expect(result.options.actions).toEqual([{ action: "save", title: "Save" }])
      expect(result.data.url).toBe("/")
      expect(result.payloadType).toBeUndefined()
    } finally {
      Object.defineProperty(navigator, "language", { configurable: true, value: originalLanguage })
    }
  })

  it("filters invalid actions and omits optional action metadata when none is usable", () => {
    const result = buildNotificationDetails({
      actions: [
        null as unknown as NotificationActionPayload,
        { action: " ", title: "valid-looking" },
        { action: "ok", title: "" },
      ],
    })
    expect(result.options.actions).toBeUndefined()
    expect(result.data.actionUrls).toBeUndefined()
  })
})
