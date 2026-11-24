/// <reference lib="webworker" />
declare const self: ServiceWorkerGlobalScope

/** Posted to a controlled window; the window answers on the transferred port. */
export const REQUEST_OFFLINE_REPLAY_CREDENTIALS = "REQUEST_OFFLINE_REPLAY_CREDENTIALS"
/** This request requires a fresh bootstrap and cannot be answered by an older window. */
export const REQUEST_OFFLINE_REPLAY_CREDENTIALS_V2 = "REQUEST_OFFLINE_REPLAY_CREDENTIALS_V2"

export interface OfflineReplayCredentials {
  csrfToken: string
  sessionNonce: string
}

export const REPLAY_CREDENTIAL_RESPONSE_TIMEOUT_MS = 1_000
/** Allows the bounded eight-second bootstrap plus time for its response to reach the worker. */
export const REPLAY_REFRESH_RESPONSE_TIMEOUT_MS = 9_000
const MAX_CSRF_TOKEN_LENGTH = 4_096
const MAX_SESSION_NONCE_LENGTH = 128

function isBoundedString(value: unknown, maxLength: number): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= maxLength
}

function parseCredentials(answer: unknown): OfflineReplayCredentials | null {
  if (!answer || typeof answer !== "object") return null
  const { csrfToken, sessionNonce } = answer as Partial<OfflineReplayCredentials>
  if (
    !isBoundedString(csrfToken, MAX_CSRF_TOKEN_LENGTH) ||
    !isBoundedString(sessionNonce, MAX_SESSION_NONCE_LENGTH)
  ) {
    return null
  }
  return { csrfToken, sessionNonce }
}

type CredentialRequest =
  | { type: typeof REQUEST_OFFLINE_REPLAY_CREDENTIALS }
  | {
      type: typeof REQUEST_OFFLINE_REPLAY_CREDENTIALS_V2
      version: 2
      sessionNonce: string
      expiresAt: number
    }

function askClient(
  client: Client,
  request: CredentialRequest = { type: REQUEST_OFFLINE_REPLAY_CREDENTIALS },
  timeoutMs = REPLAY_CREDENTIAL_RESPONSE_TIMEOUT_MS
): Promise<OfflineReplayCredentials | null> {
  const channel = new MessageChannel()
  let timer: ReturnType<typeof setTimeout> | undefined
  return new Promise<OfflineReplayCredentials | null>((resolve) => {
    timer = setTimeout(() => resolve(null), timeoutMs)
    channel.port1.onmessage = ({ data }) => {
      const credentials = parseCredentials(data)
      if (
        request.type === REQUEST_OFFLINE_REPLAY_CREDENTIALS_V2 &&
        (data?.version !== 2 || credentials?.sessionNonce !== request.sessionNonce)
      ) {
        resolve(null)
        return
      }
      resolve(credentials)
    }
    try {
      client.postMessage(request, [channel.port2])
    } catch {
      resolve(null)
    }
  }).finally(() => {
    clearTimeout(timer)
    channel.port1.close()
    channel.port2.close()
  })
}

/**
 * Asks each controlled window, in turn, for the CSRF token and the browser session
 * nonce it holds. A window answers only while its session is verified, so a null
 * result means no session-bound replay is currently provable.
 */
export async function requestReplayCredentials(): Promise<OfflineReplayCredentials | null> {
  try {
    for (const client of await self.clients.matchAll({ type: "window" })) {
      const credentials = await askClient(client)
      if (credentials) return credentials
    }
  } catch {
    // A worker that cannot enumerate its controlled windows has nobody to ask, so records stay held.
  }
  return null
}

/** A forced bootstrap and all candidate window answers share one bounded time budget. */
export async function requestRefreshedReplayCredentials(
  sessionNonce: string
): Promise<OfflineReplayCredentials | null> {
  if (!isBoundedString(sessionNonce, MAX_SESSION_NONCE_LENGTH)) return null
  const deadline = performance.now() + REPLAY_REFRESH_RESPONSE_TIMEOUT_MS
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    const clients = await Promise.race([
      self.clients.matchAll({ type: "window" }),
      new Promise<null>((resolve) => {
        timer = setTimeout(() => resolve(null), REPLAY_REFRESH_RESPONSE_TIMEOUT_MS)
      }),
    ])
    clearTimeout(timer)
    if (!clients) return null
    for (const client of clients) {
      const remaining = deadline - performance.now()
      if (remaining <= 0) return null
      const credentials = await askClient(
        client,
        {
          type: REQUEST_OFFLINE_REPLAY_CREDENTIALS_V2,
          version: 2,
          sessionNonce,
          expiresAt: Date.now() + Math.floor(remaining),
        },
        remaining
      )
      if (performance.now() >= deadline) return null
      if (credentials) return credentials
    }
  } catch {
    // No verified, refreshed response means that the queued write remains held.
  } finally {
    clearTimeout(timer)
  }
  return null
}
