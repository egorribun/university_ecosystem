/// <reference lib="webworker" />
declare const self: ServiceWorkerGlobalScope

/** Posted to a controlled window; the window answers on the transferred port. */
export const REQUEST_OFFLINE_REPLAY_CREDENTIALS = "REQUEST_OFFLINE_REPLAY_CREDENTIALS"

export interface OfflineReplayCredentials {
  csrfToken: string
  sessionNonce: string
}

const ANSWER_TIMEOUT_MS = 1_000
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

function askClient(client: Client): Promise<OfflineReplayCredentials | null> {
  const channel = new MessageChannel()
  let timer: ReturnType<typeof setTimeout> | undefined
  return new Promise<OfflineReplayCredentials | null>((resolve) => {
    timer = setTimeout(() => resolve(null), ANSWER_TIMEOUT_MS)
    channel.port1.onmessage = ({ data }) => resolve(parseCredentials(data))
    try {
      client.postMessage({ type: REQUEST_OFFLINE_REPLAY_CREDENTIALS }, [channel.port2])
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
