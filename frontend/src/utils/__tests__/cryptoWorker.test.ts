/* eslint-disable @typescript-eslint/no-explicit-any */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.unmock("@/utils/cryptoWorker")

const mockWorker = {
  postMessage: vi.fn(),
  onmessage: null as any,
  onerror: null as any,
}

class MockWorker {
  constructor() {
    return mockWorker
  }
}

describe("cryptoWorker wrapper", () => {
  let cryptoWorker: any

  beforeEach(async () => {
    vi.resetModules()
    vi.useFakeTimers()
    vi.clearAllMocks()

    mockWorker.onmessage = null
    mockWorker.onerror = null
    mockWorker.postMessage.mockClear()

    vi.stubGlobal("Worker", MockWorker)
    const mod = await import("../cryptoWorker")
    cryptoWorker = mod.cryptoWorker
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("handles successful pbkdf2 derivation", async () => {
    const params = { value: "password", salt: "salt", keySize: 256, iterations: 10 }
    const p = cryptoWorker.pbkdf2(params)

    expect(mockWorker.postMessage).toHaveBeenCalledTimes(1)
    const callData = (mockWorker.postMessage as any).mock.calls[0][0]
    expect(callData.type).toBe("PBKDF2")
    expect(callData.payload).toEqual(params)
    expect(typeof callData.id).toBe("string")

    mockWorker.onmessage({
      data: { id: callData.id, result: "derived-hash-value" },
    } as MessageEvent)

    const result = await p
    expect(result).toBe("derived-hash-value")
  })

  it("handles successful scrypt derivation converting results to Uint8Array", async () => {
    const params = {
      password: new Uint8Array([1, 2]),
      salt: new Uint8Array([3, 4]),
      N: 16,
      r: 1,
      p: 1,
      dkLen: 64,
    }
    const p = cryptoWorker.scrypt(params)

    const callData = (mockWorker.postMessage as any).mock.calls[0][0]
    expect(callData.type).toBe("SCRYPT")

    mockWorker.onmessage({
      data: { id: callData.id, result: [10, 20, 30] },
    } as MessageEvent)

    const result = await p
    expect(result).toBeInstanceOf(Uint8Array)
    expect(Array.from(result)).toEqual([10, 20, 30])
  })

  it("handles successful hmacSha256 derivation", async () => {
    const params = { json: '{"a": 1}', key: "secret-key" }
    const p = cryptoWorker.hmacSha256(params)

    const callData = (mockWorker.postMessage as any).mock.calls[0][0]
    expect(callData.type).toBe("HMAC_SHA256")

    mockWorker.onmessage({
      data: { id: callData.id, result: "signature" },
    } as MessageEvent)

    const result = await p
    expect(result).toBe("signature")
  })

  it("rejects when the worker returns an error", async () => {
    const p = cryptoWorker.pbkdf2({ value: "a", salt: "b", keySize: 128, iterations: 1 })
    const callData = (mockWorker.postMessage as any).mock.calls[0][0]

    mockWorker.onmessage({
      data: { id: callData.id, error: "failed calculation" },
    } as MessageEvent)

    await expect(p).rejects.toThrow("failed calculation")
  })

  it("rejects outstanding promises when the worker crashes (onerror)", async () => {
    const p1 = cryptoWorker.pbkdf2({ value: "a", salt: "b", keySize: 128, iterations: 1 })
    const p2 = cryptoWorker.hmacSha256({ json: "{}", key: "key" })

    expect(mockWorker.onerror).toBeTypeOf("function")

    mockWorker.onerror({
      message: "Worker thread crashed due to Out Of Memory",
    } as ErrorEvent)

    await expect(p1).rejects.toThrow("Worker thread crashed due to Out Of Memory")
    await expect(p2).rejects.toThrow("Worker thread crashed due to Out Of Memory")
  })

  it("rejects promises after a 30-second timeout", async () => {
    const p = cryptoWorker.pbkdf2({ value: "a", salt: "b", keySize: 128, iterations: 1 })

    // Fast forward 30 seconds
    vi.advanceTimersByTime(30000)

    await expect(p).rejects.toThrow("Crypto worker timeout after 30000ms (op: PBKDF2)")
  })

  it("ignores malformed or unrecognized messages", async () => {
    const p = cryptoWorker.pbkdf2({ value: "a", salt: "b", keySize: 128, iterations: 1 })
    const callData = (mockWorker.postMessage as any).mock.calls[0][0]

    // Send msg with invalid shape
    mockWorker.onmessage({} as MessageEvent)
    mockWorker.onmessage({ data: null } as MessageEvent)
    mockWorker.onmessage({ data: { id: 123 } } as MessageEvent)
    mockWorker.onmessage({ data: { id: "non-existent-id", result: "ok" } } as MessageEvent)

    // Verify original promise is still pending
    let resolved = false
    p.then(() => {
      resolved = true
    })

    await vi.advanceTimersByTimeAsync(1000)
    expect(resolved).toBe(false)

    // Now resolve with the proper ID
    mockWorker.onmessage({
      data: { id: callData.id, result: "ok" },
    } as MessageEvent)

    await p
    expect(resolved).toBe(true)
  })
})
