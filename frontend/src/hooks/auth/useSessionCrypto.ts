import { useCallback, useEffect, useRef, useState } from "react"
import api from "@/api/client"
import {
  SERVICE_WORKER_MESSAGE_TYPES,
  type ApiCacheControlMessage,
} from "@/constants/serviceWorkerMessages"
import { SessionSigningKeyOut } from "@/api/generated"
import { logWarning } from "@/app/logger"

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

export const hashSessionIdentifier = async (value: string): Promise<string> => {
  // Use a static salt for session ID hashing
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

// Sign snapshot, ensuring sensitive fields are scrypt-hashed with per-user salt
export const signSnapshot = async (
  payload: unknown,
  key: string,
  userSalt: string
): Promise<string> => {
  // Deep-clone and hash sensitive fields before stringification (await/async)
  const safePayload = await hashSensitiveFields(payload, userSalt)
  const json = JSON.stringify(safePayload)
  // Offload HMAC to worker
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

/** Maximum consecutive failures before giving up (resets on success or explicit key update). */
const MAX_SIGNING_KEY_RETRIES = 3

export const useSessionCrypto = () => {
  // Always initialise to null — key lives in memory only, never in Web Storage.
  // ensureSessionSigningKey() will fetch from /auth/session/signing-key on first use.
  const [sessionSigningKey, setSessionSigningKeyState] = useState<string | null>(null)
  const sessionSigningKeyRef = useRef<string | null>(sessionSigningKey)
  const sessionSigningKeyPromiseRef = useRef<Promise<string | null> | null>(null)
  /** Consecutive failure counter — reset to 0 on success or explicit updateSessionSigningKey call. */
  const signingKeyRetryCountRef = useRef(0)
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
      signingKeyRetryCountRef.current = 0  // reset circuit breaker on explicit update
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
          signingKeyRetryCountRef.current = 0
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

  useEffect(() => {
    if (sessionSigningKeyRef.current !== sessionSigningKey) {
      sessionSigningKeyRef.current = sessionSigningKey
    }
  }, [sessionSigningKey])

  useEffect(() => {
    if (typeof window === "undefined") return
    void sendSessionCacheUpdate(sessionSigningKeyRef.current, { force: true })
  }, [sendSessionCacheUpdate])

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
