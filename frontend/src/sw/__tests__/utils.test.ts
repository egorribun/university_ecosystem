import { afterEach, describe, expect, it, vi } from "vitest"

import { broadcastMessage, isOnline, sanitizeValue } from "../utils"

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("service-worker utilities", () => {
  it("treats a missing navigator as online and otherwise follows onLine", () => {
    vi.stubGlobal("self", { navigator: undefined })
    expect(isOnline()).toBe(true)

    vi.stubGlobal("self", { navigator: { onLine: true } })
    expect(isOnline()).toBe(true)

    vi.stubGlobal("self", { navigator: { onLine: false } })
    expect(isOnline()).toBe(false)
  })

  it("broadcasts a message to every window client", async () => {
    const first = { postMessage: vi.fn() }
    const second = { postMessage: vi.fn() }
    const matchAll = vi.fn().mockResolvedValue([first, second])
    vi.stubGlobal("self", { clients: { matchAll } })

    const message = { type: "SYNC_COMPLETE" }
    await broadcastMessage(message)

    expect(matchAll).toHaveBeenCalledWith({ type: "window" })
    expect(first.postMessage).toHaveBeenCalledWith(message)
    expect(second.postMessage).toHaveBeenCalledWith(message)
  })

  it("sanitizes primitives, dates, arrays, records, and unsupported values", () => {
    const date = new Date("2026-08-18T00:00:00.000Z")
    const input = {
      text: "ok",
      count: 2,
      enabled: false,
      nil: null,
      missing: undefined,
      date,
      values: ["kept", undefined, Symbol("removed"), { nested: true }],
      callback: () => "removed",
    }

    expect(sanitizeValue(input)).toEqual({
      text: "ok",
      count: 2,
      enabled: false,
      nil: null,
      date: date.toISOString(),
      values: ["kept", { nested: true }],
    })
    expect(sanitizeValue(undefined)).toBeUndefined()
    expect(sanitizeValue(Symbol("unsupported"))).toBeUndefined()
  })

  it("drops values beyond the recursion limit", () => {
    expect(sanitizeValue("too-deep", 6)).toBeUndefined()
    expect(sanitizeValue([[[[[[["too-deep"]]]]]]])).toEqual([[[[[[]]]]]])
  })
})
