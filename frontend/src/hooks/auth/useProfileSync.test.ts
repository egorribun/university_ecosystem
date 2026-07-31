import { describe, expect, it, vi } from "vitest"

import {
  PROFILE_CACHE_SCHEMA_VERSION,
  PROFILE_CACHE_STORAGE_KEY,
  currentUserQueryKey,
  encryptData,
  signPayload,
  type CachedUserSnapshot,
} from "./useProfileSync"

/**
 * useProfileSync — exposes 5 public surfaces. The hook itself
 * (the largest export) involves TanStack Query + Zustand + axios
 * interceptors; full behaviour is covered by Track D specs.
 *
 * This test pins the deterministic helpers + the exported constants
 * that other modules consume:
 *
 *  - PROFILE_CACHE_SCHEMA_VERSION — bumped on shape change to evict
 *    older caches (PII concern at v7 → v8);
 *  - PROFILE_CACHE_STORAGE_KEY — derived from the version, must end
 *    in "v8" (current schema);
 *  - currentUserQueryKey — TanStack Query key for invalidation;
 *  - encryptData — AES-GCM with PBKDF2-derived key, output format
 *    "saltHex:ivHex:ciphertextBase64";
 *  - signPayload — HMAC-SHA256 over JSON-serialised payload, base64
 *    encoded.
 */

describe("useProfileSync — public constants", () => {
  it("PROFILE_CACHE_SCHEMA_VERSION is 8", () => {
    // Lock current schema version. Bump the test together with the
    // const when a new shape ships — the on-disk cache must be evicted.
    expect(PROFILE_CACHE_SCHEMA_VERSION).toBe(8)
  })

  it("PROFILE_CACHE_STORAGE_KEY embeds the schema version", () => {
    expect(PROFILE_CACHE_STORAGE_KEY).toBe(
      `ecosystem.profile.cache.v${PROFILE_CACHE_SCHEMA_VERSION}`
    )
  })

  it("currentUserQueryKey matches the documented tuple", () => {
    expect(currentUserQueryKey).toEqual(["users", "me"])
  })
})

describe("useProfileSync — signPayload (HMAC-SHA256 base64)", () => {
  // CachedUserSnapshot is a Pick<User, ...> + optional MFA + preferences.
  // We only need the required fields populated to type-check.
  const SAMPLE_USER: CachedUserSnapshot = {
    id: "user-1",
    full_name: "Alice",
    group_id: 1,
    avatar_url: null,
    cover_url: null,
    is_active: true,
    spotify_connected: false,
  } as unknown as CachedUserSnapshot

  const VALID_SNAPSHOT = {
    version: 8,
    expiresAt: 1_700_000_000_000,
    data: SAMPLE_USER,
  } as const

  it("returns a deterministic base64 signature", async () => {
    const a = await signPayload(VALID_SNAPSHOT, "key")
    const b = await signPayload(VALID_SNAPSHOT, "key")
    expect(a).toBe(b)
    expect(a).toMatch(/^[A-Za-z0-9+/=]+$/)
    expect(a.length).toBe(44) // HMAC-SHA256 base64 is 44 chars
  })

  it("differs when the signing key changes", async () => {
    const a = await signPayload(VALID_SNAPSHOT, "key-A")
    const b = await signPayload(VALID_SNAPSHOT, "key-B")
    expect(a).not.toBe(b)
  })

  it("differs when the payload changes", async () => {
    const a = await signPayload(VALID_SNAPSHOT, "k")
    const b = await signPayload({ ...VALID_SNAPSHOT, expiresAt: 1 }, "k")
    expect(a).not.toBe(b)
  })

  it("returns empty string on internal error (catch-all)", async () => {
    // The function catches any error and returns ""; pass a value that
    // cannot be JSON-stringified (circular reference).
    const circular: Record<string, unknown> = {}
    circular.self = circular
    const sig = await signPayload(circular as unknown as Parameters<typeof signPayload>[0], "k")
    expect(sig).toBe("")
  })
})

describe("useProfileSync — encryptData (AES-GCM)", () => {
  const SNAPSHOT: CachedUserSnapshot = {
    id: "user-1",
    full_name: "Alice",
    group_id: 1,
    avatar_url: null,
    cover_url: null,
    is_active: true,
    spotify_connected: false,
  } as unknown as CachedUserSnapshot

  it("returns a string formatted as 'saltHex:ivHex:base64'", async () => {
    const out = await encryptData(SNAPSHOT, "the-key")
    expect(out).toBeTruthy()
    const parts = out!.split(":")
    expect(parts).toHaveLength(3)
    const [saltHex, ivHex, ciphertextBase64] = parts
    expect(saltHex).toMatch(/^[0-9a-f]{32}$/) // 16 bytes hex
    expect(ivHex).toMatch(/^[0-9a-f]{24}$/) // 12 bytes hex
    expect(ciphertextBase64).toMatch(/^[A-Za-z0-9+/=]+$/)
  })

  it("uses fresh salt + iv on each call (non-deterministic ciphertext)", async () => {
    const a = await encryptData(SNAPSHOT, "the-key")
    const b = await encryptData(SNAPSHOT, "the-key")
    expect(a).not.toBe(b)
    // But the format invariant holds.
    expect(a!.split(":")).toHaveLength(3)
    expect(b!.split(":")).toHaveLength(3)
  })

  it("returns null when Web Crypto is unavailable", async () => {
    const originalWindow = window
    vi.stubGlobal("window", undefined)
    try {
      await expect(encryptData(SNAPSHOT, "the-key")).resolves.toBeNull()
    } finally {
      vi.stubGlobal("window", originalWindow)
    }
  })
})
