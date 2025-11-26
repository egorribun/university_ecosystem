import { useCallback, useEffect, useRef, useState } from "react"
import api from "@/api/client"
import {
  SERVICE_WORKER_MESSAGE_TYPES,
  type ApiCacheControlMessage,
} from "@/constants/serviceWorkerMessages"
import type { components } from "@/api/generated/schema"

const PROFILE_CACHE_BASE_KEY = "ecosystem.profile.cache"
export const SESSION_SIGNING_KEY_STORAGE_KEY = `${PROFILE_CACHE_BASE_KEY}.sessionKey`

type SessionSigningKeyResponse = components["schemas"]["SessionSigningKeyOut"]

const utf8 = new TextEncoder()

const bytesToBase64 = (bytes: Uint8Array): string => {
  const maybeBuffer =
    typeof globalThis !== "undefined" &&
      typeof (globalThis as { Buffer?: unknown }).Buffer === "function"
      ? (globalThis as { Buffer?: { from?: unknown } }).Buffer
      : undefined

  if (
    maybeBuffer &&
    typeof maybeBuffer === "function" &&
    typeof (maybeBuffer as { from?: unknown }).from === "function"
  ) {
    return (
      maybeBuffer as {
        from: (
          input: Uint8Array | string,
          encoding?: string
        ) => {
          toString: (encoding: string) => string
        }
      }
    )
      .from(bytes)
      .toString("base64")
  }

  let binary = ""
  for (const byte of bytes) {
    binary += String.fromCharCode(byte)
  }

  if (typeof globalThis !== "undefined" && typeof globalThis.btoa === "function") {
    return globalThis.btoa(binary)
  }

  if (
    maybeBuffer &&
    typeof maybeBuffer === "function" &&
    typeof (maybeBuffer as { from?: unknown }).from === "function"
  ) {
    return (
      maybeBuffer as {
        from: (
          input: Uint8Array | string,
          encoding?: string
        ) => {
          toString: (encoding: string) => string
        }
      }
    )
      .from(binary, "binary")
      .toString("base64")
  }

  return binary
}

const bytesToHex = (bytes: Uint8Array): string =>
  Array.from(bytes)
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("")

import CryptoJS from "crypto-js"
import { scrypt } from "scrypt-js"

export const hashSessionIdentifier = (value: string): string => {
  // Use a static salt for session ID hashing
  const salt = CryptoJS.enc.Utf8.parse("ecosystem.session.id.salt.v1")
  // Use PBKDF2 with 100,000 iterations and SHA256
  const hash = CryptoJS.PBKDF2(value, salt, {
    keySize: 256 / 32,
    iterations: 100000,
    hasher: CryptoJS.algo.SHA256,
  })
  return hash.toString(CryptoJS.enc.Hex)
}

// Helper to hash sensitive fields for signature input using scrypt and per-user salt
async function hashSensitiveFields(obj: unknown, userSalt: string): Promise<unknown> {
  if (typeof obj !== "object" || obj === null) return obj;
  // List of sensitive fields to protect:
  const sensitiveFields = ["mfa_default_method", "mfa_last_verified_at", "mfa_required"];
  // Use per-user salt, hashed with a static string for namespace separation
  const baseSalt = "ecosystem.sensitive.field.salt.v2";
  const compositeSalt = new TextEncoder().encode(`${baseSalt}:${userSalt}`);
  if (Array.isArray(obj)) {
    return Promise.all(obj.map((item) => hashSensitiveFields(item, userSalt)));
  }
  const result: Record<string, any> = {};
  for (const key in obj) {
    if (Object.prototype.hasOwnProperty.call(obj, key)) {
      if (sensitiveFields.includes(key) && typeof (obj as any)[key] === "string") {
        // Use scrypt-js for password-based key derivation (memory hard)
        const passwordBytes = new TextEncoder().encode((obj as any)[key]);
        // N = 2^14, r = 8, p = 1 (recommended browser settings)
        const hashed = await scrypt(passwordBytes, compositeSalt, 16384, 8, 1, 32);
        result[key] = Array.from(hashed).map(b => b.toString(16).padStart(2, "0")).join("");
      } else {
        result[key] = await hashSensitiveFields((obj as any)[key], userSalt);
      }
    }
  }
  return result;
}

// Sign snapshot, ensuring sensitive fields are scrypt-hashed with per-user salt
export const signSnapshot = async (payload: unknown, key: string, userSalt: string): Promise<string> => {
  // Deep-clone and hash sensitive fields before stringification (await/async)
  const safePayload = await hashSensitiveFields(payload, userSalt);
  const json = JSON.stringify(safePayload);
  const signature = CryptoJS.HmacSHA256(json, key);
  return signature.toString(CryptoJS.enc.Base64);
}

export const readStoredSessionSigningKey = (): string | null => {
  if (typeof sessionStorage === "undefined") return null
  try {
    return sessionStorage.getItem(SESSION_SIGNING_KEY_STORAGE_KEY)
  } catch {
    return null
  }
}

const persistSessionSigningKey = (value: string | null) => {
  if (typeof sessionStorage === "undefined") return
  try {
    if (value) {
      sessionStorage.setItem(SESSION_SIGNING_KEY_STORAGE_KEY, value)
    } else {
      sessionStorage.removeItem(SESSION_SIGNING_KEY_STORAGE_KEY)
    }
  } catch {
    /* ignore */
  }
}

export const useSessionCrypto = () => {
  const [sessionSigningKey, setSessionSigningKeyState] = useState<string | null>(() =>
    readStoredSessionSigningKey()
  )
  const sessionSigningKeyRef = useRef<string | null>(sessionSigningKey)
  const sessionSigningKeyPromiseRef = useRef<Promise<string | null> | null>(null)
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
          console.warn("Failed to post message to service worker", error)
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
            console.warn("Failed to deliver message to service worker", error)
          }
        })
    }
  }, [])

  const sendSessionCacheUpdate = useCallback(
    (
      signingKey: string | null,
      { purge = false, force = false }: { purge?: boolean; force?: boolean } = {}
    ) => {
      const nextHash = signingKey ? hashSessionIdentifier(signingKey) : null
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
    (value: string | null) => {
      sessionSigningKeyRef.current = value
      setSessionSigningKeyState(value)
      persistSessionSigningKey(value)
      sendSessionCacheUpdate(value, { purge: true })
    },
    [sendSessionCacheUpdate]
  )

  const ensureSessionSigningKey = useCallback(async () => {
    if (sessionSigningKeyRef.current) {
      return sessionSigningKeyRef.current
    }
    if (sessionSigningKeyPromiseRef.current) {
      return sessionSigningKeyPromiseRef.current
    }
    const promise = (async () => {
      try {
        const response = await api.get<SessionSigningKeyResponse>("/auth/session/signing-key", {
          skipRateLimitQueue: true,
        })
        const key = response.data.signing_key
        updateSessionSigningKey(key)
        return key
      } finally {
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
    sendSessionCacheUpdate(sessionSigningKeyRef.current, { force: true })
  }, [sendSessionCacheUpdate])

  return {
    sessionSigningKey,
    sessionSigningKeyRef,
    sessionSigningKeyPromiseRef,
    updateSessionSigningKey,
    ensureSessionSigningKey,
    sendSessionCacheUpdate,
  }
}
