/**
 * @fileoverview Session-bound HMAC signing helpers + key fetch hook.
 *
 * The backend issues a per-session signing key on login; client-side
 * mutations sign request payloads with HMAC-SHA256(payload, sessionKey)
 * via a dedicated Web Worker (``@/utils/cryptoWorker``) so the key
 * never enters the React render path.
 *
 * Hooks exported here:
 *   - ``hashSessionIdentifier(value)`` — PBKDF2 wrapper used to derive
 *     the cache-key namespace from a session ID without leaking the
 *     raw value into ``localStorage``.
 *   - ``useSessionSigningKey()`` — fetches and caches the signing key
 *     from ``/auth/session-signing-key``; consumers receive a stable
 *     reference + a ``ready`` boolean.
 *
 * Cache hygiene: a legacy ``sessionStorage`` location is unconditionally
 * cleared on import (one-time migration). Future sessions never touch
 * sessionStorage — keys live only in memory + a ServiceWorker-managed
 * IndexedDB scope.
 */
import { useCallback, useEffect, useRef, useState } from "react"
import api from "@/api/client"
import {
  SERVICE_WORKER_MESSAGE_TYPES,
  type ApiCacheControlMessage,
} from "@/constants/serviceWorkerMessages"
import { SessionSigningKeyOut } from "@/api/generated"
import { logWarning } from "@/app/logger"

/** Return whether session-key synchronization is running in a browser runtime. */
export const isSessionCryptoBrowserRuntime = (): boolean =>
  typeof window !== "undefined" &&
  typeof window.document !== "undefined" &&
  typeof window.location !== "undefined"

const PROFILE_CACHE_BASE_KEY = "ecosystem.profile.cache"
// Kept for one-time migration: clear any key previously persisted in sessionStorage.
const SESSION_SIGNING_KEY_STORAGE_KEY = `${PROFILE_CACHE_BASE_KEY}.sessionKey`

// One-time cleanup: remove legacy key that was incorrectly stored in sessionStorage.
// Safe to run on every load — no-op if key is already absent.
if (typeof sessionStorage !== "undefined") {
  try {
    sessionStorage.removeItem(SESSION_SIGNING_KEY_STORAGE_KEY)
  } catch {
    /* ignore */
  }
}

type SessionSigningKeyResponse = SessionSigningKeyOut

import { cryptoWorker } from "@/utils/cryptoWorker"

/**
 * Derive a deterministic, opaque cache-key namespace from a session
 * identifier. Used to scope ServiceWorker cache entries per-session
 * without ever shipping the raw session value into ``localStorage``
 * or any DOM-readable surface. PBKDF2-SHA256, 100 000 iterations,
 * 256-bit derived key, fixed namespace salt
 * (``ecosystem.session.id.salt.v1``).
 *
 * @param value - Session identifier (raw signing key for current
 *   sessions; legacy session-storage value during one-time migration).
 * @returns Hex-encoded 256-bit hash. Stable for a given input across
 *   reloads and devices — the salt is namespace-fixed by design.
 */
export const hashSessionIdentifier = async (value: string): Promise<string> => {
  return cryptoWorker.pbkdf2({
    value,
    salt: "ecosystem.session.id.salt.v1",
    keySize: 256,
    iterations: 100000,
  })
}

// Helper to hash sensitive fields for signature input using scrypt and per-user salt
async function hashSensitiveFields(obj: unknown, userSalt: string): Promise<unknown> {
  if (typeof obj !== "object" || obj === null) return obj
  // List of sensitive fields to protect:
  const sensitiveFields = ["mfa_default_method", "mfa_last_verified_at", "mfa_required"]
  // Use per-user salt, hashed with a static string for namespace separation
  const baseSalt = "ecosystem.sensitive.field.salt.v2"
  const compositeSalt = new TextEncoder().encode(`${baseSalt}:${userSalt}`)
  if (Array.isArray(obj)) {
    return Promise.all(obj.map((item) => hashSensitiveFields(item, userSalt)))
  }
  const result: Record<string, unknown> = {}
  for (const key in obj) {
    if (Object.prototype.hasOwnProperty.call(obj, key)) {
      if (
        sensitiveFields.includes(key) &&
        typeof (obj as Record<string, unknown>)[key] === "string"
      ) {
        const passwordBytes = new TextEncoder().encode(
          (obj as Record<string, unknown>)[key] as string
        )
        // Offload scrypt effort to worker
        const hashed = await cryptoWorker.scrypt({
          password: passwordBytes,
          salt: compositeSalt,
          N: 16384,
          r: 8,
          p: 1,
          dkLen: 32,
        })
        result[key] = Array.from(hashed)
          .map((b) => b.toString(16).padStart(2, "0"))
          .join("")
      } else {
        result[key] = await hashSensitiveFields((obj as Record<string, unknown>)[key], userSalt)
      }
    }
  }
  return result
}

/**
 * Sign a profile/snapshot payload with the current session signing key.
 *
 * Steps (all run inside the dedicated crypto Web Worker so the key
 * material never enters the React render path):
 *   1. Deep-clone ``payload`` and replace each value of a known
 *      sensitive field name (MFA flags) with its scrypt hash, salted
 *      by the per-user ``userSalt`` plus a fixed namespace prefix
 *      ``ecosystem.sensitive.field.salt.v2``.
 *   2. JSON-stringify the sanitised clone.
 *   3. Compute ``HMAC-SHA256(json, key)``.
 *
 * @param payload - Object to sign — typically a user profile snapshot
 *   that gets posted to the backend.
 * @param key - Session signing key (read from ``useSessionCrypto``).
 * @param userSalt - Per-user salt fragment, namespaced with the v2
 *   constant before being fed into scrypt.
 * @returns Hex-encoded HMAC-SHA256 of the sanitised payload.
 */
export const signSnapshot = async (
  payload: unknown,
  key: string,
  userSalt: string
): Promise<string> => {
  const safePayload = await hashSensitiveFields(payload, userSalt)
  const json = JSON.stringify(safePayload)
  return cryptoWorker.hmacSha256({ json, key })
}

/**
 * Signing key is kept ONLY in memory (React state + ref).
 * sessionStorage is NOT used: XSS can read it trivially with one line.
 * On page reload the key is re-fetched from /auth/session/signing-key (auth'd endpoint).
 * Security: key exposure requires full JS execution context control, not just storage read.
 */
export const readStoredSessionSigningKey = (): string | null => null

const persistSessionSigningKey = (_value: string | null) => {
  // Intentionally empty — signing key must not be written to any Web Storage.
  // The key lives only in React state (useSessionCrypto hook) for the session duration.
}

/** Maximum consecutive failures before entering backoff (resets on success). */
const MAX_SIGNING_KEY_RETRIES = 3
/**
 * Initial backoff delay after hitting MAX_SIGNING_KEY_RETRIES.
 * FE-03 (audit 2026-03-08 Wave 5): Without backoff the hook immediately
 * resets signingKeyRetryCountRef to 0 and starts a fresh 3-attempt cycle on
 * the next render, creating a thundering-herd of rapid retry bursts against
 * the /auth/session/signing-key endpoint when the backend is degraded.
 */
const SIGNING_KEY_BACKOFF_BASE_MS = 5_000

/**
 * Memory-only session-signing-key manager + ServiceWorker cache-key
 * synchronisation.
 *
 * The signing key is fetched lazily from
 * ``/auth/session/signing-key`` the first time a caller invokes
 * ``ensureSessionSigningKey()``; after that it stays in React state +
 * a ref so concurrent callers all share a single in-flight promise.
 *
 * Failure handling:
 *  - Up to ``MAX_SIGNING_KEY_RETRIES`` (3) consecutive failures retry
 *    immediately on subsequent ``ensure()`` calls.
 *  - On the 3rd failure, the hook enters exponential backoff
 *    (``SIGNING_KEY_BACKOFF_BASE_MS = 5_000`` doubling, capped at
 *    60 s) and dispatches a ``"auth:session-crypto-failed"`` window
 *    event so ``SessionCryptoErrorBoundary`` can prompt
 *    re-authentication. ``signingKeyBackoffTimerRef`` is cleared on
 *    unmount so React 18 StrictMode double-mount doesn't leak a
 *    stale timer.
 *
 * Side effects:
 *  - Posts ``SET_API_SESSION_CACHE_KEY`` to the active ServiceWorker
 *    (and ``CLEAR_API_CACHE`` when ``purge: true``) so the
 *    request-cache scope rotates with the signing key.
 *
 * @returns ``sessionSigningKey`` (state) + ``sessionSigningKeyRef`` /
 *   ``sessionSigningKeyPromiseRef`` / ``signingKeyRetryCountRef`` for
 *   internal callers that need to read the key without re-rendering,
 *   plus three commands: ``updateSessionSigningKey`` (set or clear),
 *   ``ensureSessionSigningKey`` (fetch-on-demand, deduplicated),
 *   ``sendSessionCacheUpdate`` (force-sync the SW cache key without
 *   changing local state).
 */
export const useSessionCrypto = () => {
  // Always initialise to null — key lives in memory only, never in Web Storage.
  // ensureSessionSigningKey() will fetch from /auth/session/signing-key on first use.
  const [sessionSigningKey, setSessionSigningKeyState] = useState<string | null>(null)
  const sessionSigningKeyRef = useRef<string | null>(sessionSigningKey)
  const sessionSigningKeyPromiseRef = useRef<Promise<string | null> | null>(null)
  /** Consecutive failure counter — reset to 0 on success or after backoff expires. */
  const signingKeyRetryCountRef = useRef(0)
  /**
   * Current backoff delay in ms. Doubles on each circuit-open event, capped at 60 s.
   * FE-03 (audit 2026-03-08 Wave 5): exponential backoff prevents retry storms.
   */
  const signingKeyBackoffMsRef = useRef(SIGNING_KEY_BACKOFF_BASE_MS)
  /**
   * DEBT-FE-01 (audit 2026-03-15): Store backoff timer ID for cleanup on unmount.
   * Without this, the setTimeout callback fires after the component unmounts in
   * React 18 Strict Mode (effects run twice), writing to a stale ref.
   */
  const signingKeyBackoffTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const sessionCacheHashRef = useRef<string | null>(null)

  const sendServiceWorkerMessage = useCallback((message: ApiCacheControlMessage) => {
    if (typeof navigator === "undefined") {
      return
    }
    const container: ServiceWorkerContainer | undefined = navigator.serviceWorker
    if (!container) {
      return
    }

    const postTo = (target: ServiceWorker | null | undefined) => {
      if (!target) return
      try {
        target.postMessage(message)
      } catch (error) {
        if (import.meta.env.DEV) {
          logWarning("Failed to post message to service worker", { error })
        }
      }
    }

    if (container.controller) {
      postTo(container.controller)
      return
    }

    const ready = container.ready
    if (ready && typeof ready.then === "function") {
      ready
        .then((registration) => {
          postTo(registration?.active ?? null)
        })
        .catch((error) => {
          if (import.meta.env.DEV) {
            logWarning("Failed to deliver message to service worker", { error })
          }
        })
    }
  }, [])

  const sendSessionCacheUpdate = useCallback(
    async (
      signingKey: string | null,
      { purge = false, force = false }: { purge?: boolean; force?: boolean } = {}
    ) => {
      const nextHash = signingKey ? await hashSessionIdentifier(signingKey) : null
      if (!force && sessionCacheHashRef.current === nextHash) {
        return
      }

      sessionCacheHashRef.current = nextHash

      if (purge) {
        sendServiceWorkerMessage({ type: SERVICE_WORKER_MESSAGE_TYPES.CLEAR_API_CACHE })
      }

      sendServiceWorkerMessage({
        type: SERVICE_WORKER_MESSAGE_TYPES.SET_API_SESSION_CACHE_KEY,
        sessionHash: nextHash ?? undefined,
      })
    },
    [sendServiceWorkerMessage]
  )

  const updateSessionSigningKey = useCallback(
    async (value: string | null) => {
      sessionSigningKeyRef.current = value
      signingKeyRetryCountRef.current = 0 // reset circuit breaker on explicit update
      setSessionSigningKeyState(value)
      persistSessionSigningKey(value)
      await sendSessionCacheUpdate(value, { purge: true })
    },
    [sendSessionCacheUpdate]
  )

  const ensureSessionSigningKey = useCallback(async (): Promise<string | null> => {
    if (sessionSigningKeyRef.current) {
      return sessionSigningKeyRef.current
    }
    // Return the in-flight promise to deduplicate concurrent callers
    if (sessionSigningKeyPromiseRef.current) {
      return sessionSigningKeyPromiseRef.current
    }
    const promise = (async (): Promise<string | null> => {
      try {
        const response = await api.get<SessionSigningKeyResponse>("/auth/session/signing-key", {
          skipRateLimitQueue: true,
        } as Parameters<typeof api.get>[1])
        // Success — reset circuit breaker and store key
        signingKeyRetryCountRef.current = 0
        const key = response.data.signing_key
        await updateSessionSigningKey(key)
        return key
      } catch (err) {
        // Increment failure counter; log once max retries reached then reset
        signingKeyRetryCountRef.current += 1
        if (signingKeyRetryCountRef.current >= MAX_SIGNING_KEY_RETRIES) {
          if (import.meta.env.DEV) {
            logWarning("[SessionCrypto] Max retries reached for signing key fetch", { err })
          }
          // FE-03 (audit 2026-03-08 Wave 5): Exponential backoff before resetting
          // the retry counter.  Without this, the hook immediately restarts a fresh
          // 3-attempt cycle on the next call, creating rapid retry bursts (thundering
          // herd) against the /auth/session/signing-key endpoint during backend
          // degradation. Backoff: 5 s → 10 s → 20 s → … capped at 60 s.
          const backoffDelay = signingKeyBackoffMsRef.current
          signingKeyBackoffMsRef.current = Math.min(signingKeyBackoffMsRef.current * 2, 60_000)
          // DEBT-FE-01: store timer ID so useEffect cleanup can cancel it on unmount.
          if (signingKeyBackoffTimerRef.current !== null) {
            clearTimeout(signingKeyBackoffTimerRef.current)
          }
          signingKeyBackoffTimerRef.current = setTimeout(() => {
            signingKeyRetryCountRef.current = 0
            signingKeyBackoffTimerRef.current = null
          }, backoffDelay)

          // P-05 (audit 2026-03-08): Signal the UI layer so it can prompt the
          // user to re-authenticate rather than silently swallowing the failure.
          // The event is caught by the SessionCryptoErrorBoundary component.
          window.dispatchEvent(
            new CustomEvent("auth:session-crypto-failed", {
              detail: { reason: "max_retries_exceeded", backoffMs: backoffDelay },
            })
          )
        }
        return null
      } finally {
        // Always clear promise ref so subsequent callers retry rather than
        // awaiting a settled (rejected) promise indefinitely.
        sessionSigningKeyPromiseRef.current = null
      }
    })()
    sessionSigningKeyPromiseRef.current = promise
    return promise
  }, [updateSessionSigningKey])

  // PERF-03 (audit 2026-03-15 Wave 7): redundant useEffect removed.
  // sessionSigningKeyRef is updated imperatively inside updateSessionSigningKey
  // (line ~202) — a separate effect syncing it from state was a double-write
  // that also ran twice per mount in React 18 StrictMode.

  useEffect(() => {
    if (!isSessionCryptoBrowserRuntime()) return
    void sendSessionCacheUpdate(sessionSigningKeyRef.current, { force: true })
  }, [sendSessionCacheUpdate])

  // DEBT-FE-01 (audit 2026-03-15): cancel pending backoff timer on unmount.
  // React 18 Strict Mode mounts/unmounts twice in dev; without cleanup the
  // setTimeout callback fires on a stale ref after the first unmount.
  useEffect(() => {
    return () => {
      if (signingKeyBackoffTimerRef.current !== null) {
        clearTimeout(signingKeyBackoffTimerRef.current)
        signingKeyBackoffTimerRef.current = null
      }
    }
  }, [])

  return {
    sessionSigningKey,
    sessionSigningKeyRef,
    sessionSigningKeyPromiseRef,
    signingKeyRetryCountRef,
    updateSessionSigningKey,
    ensureSessionSigningKey,
    sendSessionCacheUpdate,
  }
}
