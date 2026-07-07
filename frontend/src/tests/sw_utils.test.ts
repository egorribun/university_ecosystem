import { describe, expect, test, vi } from "vitest"
import { isOnline, broadcastMessage, sanitizeValue } from "@/sw/utils"
import { warn, error } from "@/sw/logger"

describe("Service Worker Utils", () => {
  test("isOnline returns true/false based on navigator", () => {
    const originalNavigator = globalThis.navigator

    // 1. undefined navigator
    Object.defineProperty(globalThis, "navigator", {
      value: undefined,
      writable: true,
      configurable: true,
    })
    expect(isOnline()).toBe(true)

    // 2. online = false
    Object.defineProperty(globalThis, "navigator", {
      value: { onLine: false },
      writable: true,
      configurable: true,
    })
    expect(isOnline()).toBe(false)

    // 3. online = true
    Object.defineProperty(globalThis, "navigator", {
      value: { onLine: true },
      writable: true,
      configurable: true,
    })
    expect(isOnline()).toBe(true)

    // restore
    Object.defineProperty(globalThis, "navigator", {
      value: originalNavigator,
      writable: true,
      configurable: true,
    })
  })

  test("broadcastMessage sends messages to window clients", async () => {
    const mockPostMessage = vi.fn()
    const mockClients = {
      matchAll: vi.fn(async () => [
        { postMessage: mockPostMessage },
        { postMessage: mockPostMessage },
      ]),
    }

    const originalSelf = globalThis.self
    Object.defineProperty(globalThis, "self", {
      value: {
        clients: mockClients,
      },
      writable: true,
      configurable: true,
    })

    await broadcastMessage({ hello: "world" })
    expect(mockPostMessage).toHaveBeenCalledTimes(2)
    expect(mockPostMessage).toHaveBeenCalledWith({ hello: "world" })

    Object.defineProperty(globalThis, "self", {
      value: originalSelf,
      writable: true,
      configurable: true,
    })
  })

  test("sanitizeValue strips deep objects and filters values", () => {
    expect(sanitizeValue(null)).toBeNull()
    expect(sanitizeValue(undefined)).toBeUndefined()
    expect(sanitizeValue(123)).toBe(123)
    expect(sanitizeValue("test")).toBe("test")
    expect(sanitizeValue(true)).toBe(true)

    const date = new Date()
    expect(sanitizeValue(date)).toBe(date.toISOString())

    // Array
    expect(sanitizeValue([123, null, undefined, "ok"])).toEqual([123, null, "ok"])

    // Object
    expect(sanitizeValue({ a: 1, b: undefined, c: { d: "nested" } })).toEqual({
      a: 1,
      c: { d: "nested" },
    })

    // Max depth
    const deep = { a: { b: { c: { d: { e: { f: "too_deep" } } } } } }
    expect(sanitizeValue(deep)).toEqual({ a: { b: { c: { d: { e: {} } } } } })

    // Unsupported type
    expect(sanitizeValue(() => {})).toBeUndefined()
  })

  test("logger warn and error under DEV mode", () => {
    const originalDev = import.meta.env.DEV
    import.meta.env.DEV = true

    const spyWarn = vi.spyOn(console, "warn").mockImplementation(() => {})
    const spyError = vi.spyOn(console, "error").mockImplementation(() => {})

    warn("test warn")
    error("test error")

    expect(spyWarn).toHaveBeenCalledWith("[SW]", "test warn")
    expect(spyError).toHaveBeenCalledWith("[SW]", "test error")

    spyWarn.mockRestore()
    spyError.mockRestore()
    import.meta.env.DEV = originalDev
  })
})
