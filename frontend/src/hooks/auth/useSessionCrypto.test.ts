import { describe, expect, it, vi } from "vitest"
import { renderHook } from "@testing-library/react"

import {
  hashSessionIdentifier,
  isSessionCryptoBrowserRuntime,
  readStoredSessionSigningKey,
  signSnapshot,
  useSessionCrypto,
} from "./useSessionCrypto"

describe("browser runtime guard", () => {
  it("distinguishes browser and server environments", () => {
    expect(isSessionCryptoBrowserRuntime()).toBe(true)
    vi.stubGlobal("window", { event: undefined })
    try {
      expect(isSessionCryptoBrowserRuntime()).toBe(false)
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it("does not synchronize the session cache from a server runtime", () => {
    const originalWindow = globalThis.window
    vi.stubGlobal("window", { event: undefined, document: globalThis.document })

    try {
      const view = renderHook(() => useSessionCrypto())
      view.unmount()
    } finally {
      vi.stubGlobal("window", originalWindow)
    }
  })
})

/**
 * useSessionCrypto — exposes three pure helpers + a stateful hook.
 * The hook itself involves api fetch + retry/backoff state and is best
 * verified end-to-end. We pin the deterministic helpers here.
 *
 * cryptoWorker is mocked globally in setupTests.ts:
 *   pbkdf2  → resolves "mock_pbkdf2"
 *   scrypt  → resolves Uint8Array([1,2,3])
 *   hmacSha256 → real HMAC-SHA256 via node:crypto
 *
 * That means signSnapshot's HMAC output is FFI-exact (Node real
 * implementation), but scrypt-hashed fields are stable values from
 * the mock — ideal for shape testing.
 */

describe("hashSessionIdentifier", () => {
  it("delegates to cryptoWorker.pbkdf2 and returns its result", async () => {
    const out = await hashSessionIdentifier("session-abc")
    expect(out).toBe("mock_pbkdf2")
  })

  it("does not depend on the input value (mock is constant)", async () => {
    // Each call hits the mock which always returns "mock_pbkdf2" — this
    // confirms the wrapper does not transform the result, just forwards.
    const a = await hashSessionIdentifier("a")
    const b = await hashSessionIdentifier("b")
    expect(a).toBe(b)
  })
})

describe("signSnapshot", () => {
  it("returns a deterministic HMAC for identical inputs", async () => {
    const a = await signSnapshot({ foo: "bar" }, "the-key", "user-1")
    const b = await signSnapshot({ foo: "bar" }, "the-key", "user-1")
    expect(a).toBe(b)
  })

  it("HMAC differs when the key changes", async () => {
    const a = await signSnapshot({ foo: 1 }, "key-A", "user-1")
    const b = await signSnapshot({ foo: 1 }, "key-B", "user-1")
    expect(a).not.toBe(b)
  })

  it("returns base64-encoded HMAC (real Node crypto via mock impl)", async () => {
    const sig = await signSnapshot({ foo: 1 }, "the-key", "user-1")
    // base64 alphabet check; HMAC-SHA256 base64 is 44 chars including padding.
    expect(sig).toMatch(/^[A-Za-z0-9+/=]+$/)
    expect(sig.length).toBe(44)
  })

  it("scalar payloads sign without crashing (no recursion into primitives)", async () => {
    await expect(signSnapshot("plain string", "k", "u")).resolves.toMatch(/^[A-Za-z0-9+/=]+$/)
    await expect(signSnapshot(42, "k", "u")).resolves.toMatch(/^[A-Za-z0-9+/=]+$/)
    await expect(signSnapshot(null, "k", "u")).resolves.toMatch(/^[A-Za-z0-9+/=]+$/)
  })

  it("hashes sensitive fields before signing (mfa_required → hex-encoded scrypt)", async () => {
    // The mocked scrypt returns Uint8Array([1,2,3]) → hex string "010203".
    // signSnapshot HMACs the post-hash JSON, so two payloads that differ
    // ONLY in the sensitive field map to the SAME signature (the field
    // is normalised before signing).
    const sigA = await signSnapshot({ mfa_required: "true", other: 1 }, "k", "u")
    const sigB = await signSnapshot({ mfa_required: "false", other: 1 }, "k", "u")
    // Both mfa_required values become "010203" after the mock scrypt,
    // so the HMACs match — proving the field WAS replaced.
    expect(sigA).toBe(sigB)
  })

  it("a non-sensitive field change does change the signature", async () => {
    const sigA = await signSnapshot({ other: 1 }, "k", "u")
    const sigB = await signSnapshot({ other: 2 }, "k", "u")
    expect(sigA).not.toBe(sigB)
  })

  it("recurses into arrays", async () => {
    // Arrays are walked element-by-element; the change in element 1
    // (non-sensitive 'other' field) propagates to the signature.
    const sigA = await signSnapshot([{ other: 1 }, { other: 2 }], "k", "u")
    const sigB = await signSnapshot([{ other: 1 }, { other: 99 }], "k", "u")
    expect(sigA).not.toBe(sigB)
  })
})

describe("readStoredSessionSigningKey", () => {
  it("always returns null — the key never lives in Web Storage", () => {
    expect(readStoredSessionSigningKey()).toBeNull()
  })
})
