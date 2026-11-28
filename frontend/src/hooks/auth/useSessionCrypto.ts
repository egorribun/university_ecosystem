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
  invalidateSessionEpoch,
  getSessionEpoch,
  isCurrentBrowserSession,
  rotateBrowserSession,
  getBrowserSessionGeneration,
  establishBrowserSession,
  matchesBrowserSession,
} from "@/stores/sessionEpoch"
import {
  SERVICE_WORKER_MESSAGE_TYPES,
  type ApiCacheControlMessage,
} from "@/constants/serviceWorkerMessages"
import { SessionSigningKeyOut } from "@/api/generated"
import { logWarning } from "@/app/logger"

/** Return whether session-key synchronization is running in a browser runtime. */
export function isSessionCryptoBrowserRuntime(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.document !== "undefined" &&
    typeof window.location !== "undefined"
  )
}

/** Read the legacy storage location through a total, shape-stable contract. */
const readLegacySessionStorage = (): Storage | null => {
  try {
    return globalThis.sessionStorage ?? null
  } catch (error) {
    if (import.meta.env.DEV) {
      logWarning("Failed to access legacy session storage", { error })
    }
    return null
  }
}

/** Remove the legacy session signing key without allowing storage failures to
 * interrupt module initialization or authentication state.  Keeping the
 * cleanup behind an explicit function makes the security boundary directly
 * testable and avoids a slow module re-import for every mutation case. */
export const clearLegacySessionSigningKey = (): void => {
  const storage = readLegacySessionStorage()
  try {
    // Keep the migration key at the call site: its value is part of the
    // observable cleanup contract and must not be hidden in import-time state.
    storage?.removeItem("ecosystem.profile.cache.sessionKey")
  } catch {
    // Storage APIs can fail even after the getter succeeds. Keep the cleanup
    // non-fatal, but surface the failure in development without including the
    // legacy key or any user data in telemetry.
    if (import.meta.env.DEV) {
      logWarning("Failed to remove legacy session signing key")
    }
  }
}

// One-time cleanup: remove legacy key that was incorrectly stored in
// sessionStorage. Safe to run on every load — no-op if key is absent.
clearLegacySessionSigningKey()

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
  const record = obj as Record<string, unknown>
  for (const key in obj) {
    if (Object.prototype.hasOwnProperty.call(obj, key)) {
      const value = record[key]
      if (sensitiveFields.includes(key) && typeof value === "string") {
        const passwordBytes = new TextEncoder().encode(value)
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
      } else if (typeof value === "object" && value !== null) {
        const nestedValue = await hashSensitiveFields(value, userSalt)
        // Keep arrays as arrays while materialising object descendants as a
        // fresh record.  Apart from preserving the payload contract, this
        // makes the object-only branch meaningful: accidentally recursing on
        // a scalar cannot silently become an identity operation.
        result[key] = Array.isArray(value)
          ? nestedValue
          : { ...(nestedValue as Record<string, unknown>) }
      } else {
        result[key] = value
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
export function readStoredSessionSigningKey(): string | null {
  return null
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
 *    60 s). Calls return null without fetching while the timer is pending.
 *    A ``"auth:session-crypto-failed"`` window event reports the delay.
 *    Successful or explicit key updates reset backoff.
 *    ``signingKeyBackoffTimerRef`` is cleared on
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
type SessionCacheAcknowledgement = {
  pending: Promise<string | null>
  controller: ServiceWorker
  port: MessagePort
  result: Promise<boolean>
  active: boolean
  finish: (applied: boolean) => void
}

const createSessionCacheAcknowledgement = (
  pending: Promise<string | null>,
  controller: ServiceWorker
): SessionCacheAcknowledgement => {
  const channel = new MessageChannel()
  let resolveResult!: (applied: boolean) => void
  const result = new Promise<boolean>((resolve) => {
    resolveResult = resolve
  })
  const acknowledgement: SessionCacheAcknowledgement = {
    pending,
    controller,
    port: channel.port2,
    result,
    active: true,
    finish(applied) {
      if (!acknowledgement.active) return
      acknowledgement.active = false
      clearTimeout(timer)
      try {
        channel.port1.close()
      } catch {
        // A worker timeout or transition may have already closed the port.
      }
      try {
        channel.port2.close()
      } catch {
        // The transferred port may already be detached.
      }
      resolveResult(applied)
    },
  }
  // Match the worker's existing identity-query deadline.
  const timer = setTimeout(() => acknowledgement.finish(false), 1000)
  channel.port1.onmessage = ({ data }) => acknowledgement.finish(data === true)
  return acknowledgement
}

export const useSessionCrypto = () => {
  // Always initialise to null — key lives in memory only, never in Web Storage.
  // ensureSessionSigningKey() will fetch from /auth/session/signing-key on first use.
  const [sessionSigningKey, setSessionSigningKeyState] = useState<string | null>(null)
  const sessionSigningKeyRef = useRef<string | null>(sessionSigningKey)
  const sessionSigningKeyPromiseRef = useRef<Promise<string | null> | null>(null)
  // Keep the server-key acquisition visible through its cache-key derivation.
  const sessionKeyReadinessRef = useRef<Promise<string | null> | null>(null)
  const sessionCacheAckRef = useRef<SessionCacheAcknowledgement | null>(null)
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
  const sessionCacheNonceRef = useRef<string | null>(null)
  const sessionRevisionRef = useRef(0)
  const cacheRevisionRef = useRef(0)

  const sendServiceWorkerMessage = useCallback(
    (message: ApiCacheControlMessage, acknowledgement?: SessionCacheAcknowledgement) => {
      const container: ServiceWorkerContainer | undefined = globalThis.navigator?.serviceWorker
      if (!container) {
        acknowledgement?.finish(false)
        return
      }

      const revision = cacheRevisionRef.current
      const postTo = (target: ServiceWorker | null | undefined) => {
        if (!target || revision !== cacheRevisionRef.current) {
          acknowledgement?.finish(false)
          return
        }
        try {
          if (
            acknowledgement?.active &&
            target === acknowledgement.controller &&
            container.controller === acknowledgement.controller
          ) {
            target.postMessage(message, [acknowledgement.port])
          } else {
            acknowledgement?.finish(false)
            target.postMessage(message)
          }
        } catch (error) {
          acknowledgement?.finish(false)
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
            acknowledgement?.finish(false)
            if (import.meta.env.DEV) {
              logWarning("Failed to deliver message to service worker", { error })
            }
          })
      } else {
        acknowledgement?.finish(false)
      }
    },
    []
  )

  const sendSessionCacheUpdate = useCallback(
    async (
      signingKey: string | null,
      {
        purge = false,
        force = false,
        confirmReadiness = false,
        resumable = false,
      }: {
        purge?: boolean
        force?: boolean
        confirmReadiness?: boolean
        resumable?: boolean
      } = {}
    ) => {
      const revision = ++cacheRevisionRef.current
      const generation = getBrowserSessionGeneration()
      if (!signingKey && !purge) return
      if (signingKey && sessionCacheNonceRef.current && sessionCacheNonceRef.current !== generation)
        return
      // Disable the old namespace before any asynchronous key derivation. A page's
      // first key only suspends it: the worker keeps responses already in flight
      // solely if this page then restores exactly the same session scope.
      if (purge || !signingKey) {
        sessionCacheHashRef.current = null
        sendServiceWorkerMessage({
          type:
            resumable && signingKey
              ? SERVICE_WORKER_MESSAGE_TYPES.SUSPEND_API_CACHE
              : SERVICE_WORKER_MESSAGE_TYPES.CLEAR_API_CACHE,
        })
      }
      const nextHash = signingKey ? await hashSessionIdentifier(signingKey) : null
      if (revision !== cacheRevisionRef.current || generation !== getBrowserSessionGeneration())
        return
      if (nextHash) {
        const nonce = sessionCacheNonceRef.current ?? establishBrowserSession(nextHash, generation)
        if (!nonce || !matchesBrowserSession(nextHash, nonce)) return
        sessionCacheNonceRef.current = nonce
      }
      if (!force && !purge && sessionCacheHashRef.current === nextHash) return
      sessionCacheHashRef.current = nextHash

      const pending = sessionKeyReadinessRef.current
      let acknowledgement = confirmReadiness ? sessionCacheAckRef.current : null
      const controller = globalThis.navigator?.serviceWorker?.controller
      if (
        confirmReadiness &&
        nextHash &&
        pending &&
        controller &&
        (!acknowledgement ||
          !acknowledgement.active ||
          acknowledgement.pending !== pending ||
          acknowledgement.controller !== controller)
      ) {
        acknowledgement?.finish(false)
        try {
          acknowledgement = createSessionCacheAcknowledgement(pending, controller)
          sessionCacheAckRef.current = acknowledgement
        } catch {
          acknowledgement = null
          sessionCacheAckRef.current = null
          // Continue with the existing unacknowledged worker path.
        }
      }
      const matchingAcknowledgement = acknowledgement?.pending === pending ? acknowledgement : null
      sendServiceWorkerMessage(
        {
          type: SERVICE_WORKER_MESSAGE_TYPES.SET_API_SESSION_CACHE_KEY,
          sessionHash: nextHash ?? undefined,
          ...(nextHash ? { sessionScope: `${nextHash}:${sessionCacheNonceRef.current}` } : {}),
        },
        matchingAcknowledgement ?? undefined
      )
      if (matchingAcknowledgement?.active) await matchingAcknowledgement.result
    },
    [sendServiceWorkerMessage]
  )

  const updateSessionSigningKey = useCallback(
    async (
      value: string | null,
      onInstall?: (revision: number, generation: string | null) => void
    ) => {
      // Only a page without any earlier key is bootstrapping; a key change clears.
      const firstKey = sessionSigningKeyRef.current === null
      if (value !== sessionSigningKeyRef.current) {
        if (
          sessionCacheHashRef.current &&
          sessionCacheNonceRef.current &&
          matchesBrowserSession(sessionCacheHashRef.current, sessionCacheNonceRef.current)
        )
          rotateBrowserSession()
        invalidateSessionEpoch()
        sessionCacheNonceRef.current = null
      }
      sessionRevisionRef.current += 1
      sessionSigningKeyPromiseRef.current = null
      if (!onInstall) {
        sessionKeyReadinessRef.current = null
        sessionCacheAckRef.current?.finish(false)
        sessionCacheAckRef.current = null
      }
      sessionSigningKeyRef.current = value
      signingKeyRetryCountRef.current = 0 // reset circuit breaker on explicit update
      signingKeyBackoffMsRef.current = SIGNING_KEY_BACKOFF_BASE_MS
      if (signingKeyBackoffTimerRef.current !== null) {
        clearTimeout(signingKeyBackoffTimerRef.current)
        signingKeyBackoffTimerRef.current = null
      }
      // Hand off this installation before cache delivery or hashing can yield.
      onInstall?.(sessionRevisionRef.current, getBrowserSessionGeneration())
      setSessionSigningKeyState(value)
      await sendSessionCacheUpdate(value, {
        purge: true,
        confirmReadiness: !!onInstall,
        resumable: firstKey,
      })
    },
    [sendSessionCacheUpdate]
  )

  const ensureSessionSigningKey = useCallback(async (): Promise<string | null> => {
    // The key ref may be installed before its cache scope reaches the worker.
    // All callers of this same acquisition must await its completion.
    if (sessionSigningKeyPromiseRef.current) return sessionSigningKeyPromiseRef.current
    if (sessionKeyReadinessRef.current) return sessionKeyReadinessRef.current
    if (sessionSigningKeyRef.current) return sessionSigningKeyRef.current
    if (signingKeyBackoffTimerRef.current !== null) {
      return null
    }
    const revision = sessionRevisionRef.current
    const generation = getBrowserSessionGeneration()
    const clearInFlightPromise = () => {
      // Always clear the ref so subsequent callers retry rather than awaiting
      // a settled promise indefinitely, regardless of fulfillment or rejection.
      if (sessionSigningKeyPromiseRef.current === promise)
        sessionSigningKeyPromiseRef.current = null
      if (sessionKeyReadinessRef.current === promise) sessionKeyReadinessRef.current = null
      const acknowledgement = sessionCacheAckRef.current
      if (acknowledgement?.pending === promise && !acknowledgement.active)
        sessionCacheAckRef.current = null
    }
    const promise = (async (): Promise<string | null> => {
      let failureRevision = revision
      let failureGeneration = generation
      try {
        const response = await api.get<SessionSigningKeyResponse>("/auth/session/signing-key", {
          skipRateLimitQueue: true,
        } as Parameters<typeof api.get>[1])
        if (revision !== sessionRevisionRef.current || generation !== getBrowserSessionGeneration())
          return null
        // Success — reset circuit breaker and store key
        signingKeyRetryCountRef.current = 0
        const key = response.data.signing_key
        await updateSessionSigningKey(key, (installedRevision, installedGeneration) => {
          failureRevision = installedRevision
          failureGeneration = installedGeneration
        })
        const hash = sessionCacheHashRef.current
        const nonce = sessionCacheNonceRef.current
        const currentGeneration = getBrowserSessionGeneration()
        const acknowledgement = sessionCacheAckRef.current
        const currentScope = !!hash && !!nonce && matchesBrowserSession(hash, nonce)
        const ownsAcknowledgedInstall =
          acknowledgement?.pending === sessionKeyReadinessRef.current
            ? currentScope && isCurrentBrowserSession()
            : generation === currentGeneration || currentScope
        return sessionRevisionRef.current === revision + 1 && ownsAcknowledgedInstall ? key : null
      } catch (err) {
        if (
          failureRevision !== sessionRevisionRef.current ||
          failureGeneration !== getBrowserSessionGeneration()
        )
          return null
        // Increment failure counter; log when entering the next backoff window.
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
          // Admission and request ownership guarantee no live timer here.
          // Store the timer so explicit updates and unmount can cancel it.
          signingKeyBackoffTimerRef.current = setTimeout(() => {
            signingKeyRetryCountRef.current = 0
            signingKeyBackoffTimerRef.current = null
          }, backoffDelay)

          // Publish the cooldown for consumers of the authentication failure event.
          window.dispatchEvent(
            new CustomEvent("auth:session-crypto-failed", {
              detail: { reason: "max_retries_exceeded", backoffMs: backoffDelay },
            })
          )
        }
        return null
      }
    })()
    // A synchronous failure event may already have started a replacement request.
    if (revision === sessionRevisionRef.current && generation === getBrowserSessionGeneration()) {
      sessionSigningKeyPromiseRef.current = promise
      sessionKeyReadinessRef.current = promise
    }
    // Register both settlement handlers before returning the promise. This
    // preserves the old finally semantics without a synthetic uncovered branch.
    void promise.then(clearInFlightPromise, clearInFlightPromise)
    return promise
  }, [updateSessionSigningKey])

  const isCurrentSigningSession = useCallback(() => {
    const hash = sessionCacheHashRef.current
    const nonce = sessionCacheNonceRef.current
    return !!sessionSigningKeyRef.current && !!hash && !!nonce && matchesBrowserSession(hash, nonce)
  }, [])

  // PERF-03 (audit 2026-03-15 Wave 7): redundant useEffect removed.
  // sessionSigningKeyRef is updated imperatively inside updateSessionSigningKey
  // (line ~202) — a separate effect syncing it from state was a double-write
  // that also ran twice per mount in React 18 StrictMode.

  useEffect(() => {
    if (!isSessionCryptoBrowserRuntime()) return
    const container = globalThis.navigator?.serviceWorker
    const sync = () => {
      const acknowledgement = sessionCacheAckRef.current
      if (acknowledgement && acknowledgement.controller !== container?.controller)
        acknowledgement.finish(false)
      void sendSessionCacheUpdate(sessionSigningKeyRef.current, { force: true })
    }
    sync()
    const onMessage = (event: MessageEvent) => {
      if (
        event.source !== container?.controller ||
        event.data?.type !== SERVICE_WORKER_MESSAGE_TYPES.REQUEST_API_SESSION_CACHE_KEY
      )
        return
      const port = event.ports[0]
      if (!port) return
      const reply = (owned = true) => {
        const nonce = sessionCacheNonceRef.current
        const candidate = sessionSigningKeyRef.current ? sessionCacheHashRef.current : null
        const hash =
          owned && candidate && nonce && matchesBrowserSession(candidate, nonce) ? candidate : null
        try {
          port.postMessage({
            sessionHash: hash,
            sessionScope: hash && nonce ? `${hash}:${nonce}` : null,
          })
        } catch {
          // The worker may have timed out and closed its reply channel.
        }
      }
      // Do not start a new key fetch in response to a worker query. If the
      // regular bootstrap is already in flight, wait for its owned result.
      const previousAcknowledgement = sessionCacheAckRef.current
      const pending =
        sessionKeyReadinessRef.current ??
        (previousAcknowledgement?.active ? previousAcknowledgement.pending : null)
      if (!pending) {
        reply()
        return
      }
      const generation = getBrowserSessionGeneration()
      if (!generation || !isCurrentBrowserSession() || !container?.controller) {
        reply(false)
        return
      }
      const startingKey = sessionSigningKeyRef.current
      const revision = sessionRevisionRef.current
      const epoch = getSessionEpoch()
      const install = startingKey ? 0 : 1
      let acknowledgement = previousAcknowledgement
      if (!acknowledgement || acknowledgement.pending !== pending) {
        try {
          acknowledgement = createSessionCacheAcknowledgement(pending, container!.controller!)
        } catch {
          reply(false)
          return
        }
        sessionCacheAckRef.current = acknowledgement
        const created = acknowledgement
        void pending.then(
          (key) => {
            if (!key || !isCurrentBrowserSession() || generation !== getBrowserSessionGeneration())
              created.finish(false)
          },
          () => created.finish(false)
        )
        void created.result.then(() => {
          if (sessionKeyReadinessRef.current !== pending && sessionCacheAckRef.current === created)
            sessionCacheAckRef.current = null
        })
      }
      void acknowledgement.result.then(async (applied) => {
        const key = applied ? await pending.catch(() => null) : null
        reply(
          !!key &&
            sessionSigningKeyRef.current === key &&
            sessionRevisionRef.current === revision + install &&
            getSessionEpoch() === epoch + install &&
            getBrowserSessionGeneration() === generation &&
            isCurrentBrowserSession() &&
            event.source === container?.controller
        )
      })
    }
    container?.addEventListener?.("controllerchange", sync)
    container?.addEventListener?.("message", onMessage)
    return () => {
      container?.removeEventListener?.("controllerchange", sync)
      container?.removeEventListener?.("message", onMessage)
    }
  }, [sendSessionCacheUpdate])

  // DEBT-FE-01 (audit 2026-03-15): cancel pending backoff timer on unmount.
  // React 18 Strict Mode mounts/unmounts twice in dev; without cleanup the
  // setTimeout callback fires on a stale ref after the first unmount.
  useEffect(() => {
    return () => {
      sessionRevisionRef.current += 1
      cacheRevisionRef.current += 1
      sessionKeyReadinessRef.current = null
      sessionCacheAckRef.current?.finish(false)
      sessionCacheAckRef.current = null
      if (signingKeyBackoffTimerRef.current !== null) {
        clearTimeout(signingKeyBackoffTimerRef.current)
        signingKeyBackoffTimerRef.current = null
      }
    }
  }, [])

  return {
    sessionSigningKey,
    isCurrentSigningSession,
    sessionSigningKeyRef,
    sessionSigningKeyPromiseRef,
    signingKeyRetryCountRef,
    updateSessionSigningKey,
    ensureSessionSigningKey,
    sendSessionCacheUpdate,
  }
}
