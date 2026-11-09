import { afterEach, describe, expect, it, vi } from "vitest"

describe("ensureWasmSanitizerInitialized", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.resetModules()
    vi.doUnmock("wasm-sanitizer")
  })

  it("does not initialize WASM during SSR", async () => {
    const initialize = vi.fn(async () => undefined)
    vi.doMock("wasm-sanitizer", () => ({ default: initialize }))
    vi.stubGlobal("window", undefined)
    const { ensureWasmSanitizerInitialized } = await import("../wasmSanitizer")

    await expect(ensureWasmSanitizerInitialized()).resolves.toBe(false)
    expect(initialize).not.toHaveBeenCalled()
  })

  it("shares one browser initialization across concurrent callers", async () => {
    let complete: (() => void) | undefined
    const pending = new Promise<void>((resolve) => {
      complete = resolve
    })
    const initialize = vi.fn(() => pending)
    vi.doMock("wasm-sanitizer", () => ({ default: initialize }))
    const { ensureWasmSanitizerInitialized } = await import("../wasmSanitizer")

    const first = ensureWasmSanitizerInitialized()
    const second = ensureWasmSanitizerInitialized()
    expect(second).toBe(first)
    await Promise.resolve()
    expect(initialize).toHaveBeenCalledTimes(1)

    complete?.()
    await expect(first).resolves.toBe(true)
    await expect(ensureWasmSanitizerInitialized()).resolves.toBe(true)
    expect(initialize).toHaveBeenCalledTimes(1)
  })

  it("returns false on a failed initialization and allows a later retry", async () => {
    const initialize = vi
      .fn<() => Promise<void>>()
      .mockRejectedValueOnce(new Error("CSP blocked WebAssembly compilation"))
      .mockResolvedValueOnce(undefined)
    vi.doMock("wasm-sanitizer", () => ({ default: initialize }))
    const { ensureWasmSanitizerInitialized } = await import("../wasmSanitizer")

    await expect(ensureWasmSanitizerInitialized()).resolves.toBe(false)
    await expect(ensureWasmSanitizerInitialized()).resolves.toBe(true)
    expect(initialize).toHaveBeenCalledTimes(2)
  })
})
