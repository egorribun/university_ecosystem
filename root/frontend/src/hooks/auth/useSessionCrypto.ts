import { useCallback, useEffect, useRef, useState } from "react"
import { hmac } from "@noble/hashes/hmac"
import { sha256 } from "@noble/hashes/sha256"
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

export const hashSessionIdentifier = (value: string): string => {
  const digest = sha256(utf8.encode(value))
  return bytesToHex(digest)
}

export const signSnapshot = (payload: unknown, key: string): string => {
  const json = JSON.stringify(payload)
  const signature = hmac(sha256, utf8.encode(key), utf8.encode(json))
  return bytesToBase64(signature)
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
