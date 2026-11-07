import { ensureCsrfCookie } from "@/api/client"
import { getBrowserSessionGeneration, isCurrentBrowserSession } from "@/stores/sessionEpoch"
import { REQUEST_OFFLINE_REPLAY_CREDENTIALS } from "./replayCredentials"

const CSRF_COOKIE_PATTERN = /(?:^|;\s*)csrf_token=([^;]*)/

/** Nonce that binds records created by this window; null when no verified session can prove one. */
export function currentReplaySessionNonce(): string | null {
  return isCurrentBrowserSession() ? getBrowserSessionGeneration() : null
}

function readCsrfCookie(): string | null {
  const value = CSRF_COOKIE_PATTERN.exec(document.cookie)?.[1]
  if (!value) return null
  try {
    // Decode exactly as the API client does before it forwards the token as a header.
    return decodeURIComponent(value)
  } catch {
    return null
  }
}

async function answerReplayCredentials(port: MessagePort): Promise<void> {
  // An unverified session is refused before any network work is started on its behalf.
  if (isCurrentBrowserSession()) {
    // A fresh page may still lack the CSRF cookie; acquire it before handing the token over.
    await ensureCsrfCookie()
  }
  // The session is checked again after the await, so a rotation during it refuses the answer.
  const sessionNonce = currentReplaySessionNonce()
  const csrfToken = sessionNonce ? readCsrfCookie() : null
  port.postMessage(sessionNonce && csrfToken ? { csrfToken, sessionNonce } : null)
}

const installedContainers = new WeakSet<ServiceWorkerContainer>()

/**
 * Answers the controlling worker's replay-credential requests. Only the controller may
 * ask, and a refusal is sent explicitly so the worker never waits out its timeout.
 */
export function installReplayCredentialResponder(container: ServiceWorkerContainer): void {
  if (installedContainers.has(container)) return
  installedContainers.add(container)
  container.addEventListener("message", (event: MessageEvent) => {
    if (event.data?.type !== REQUEST_OFFLINE_REPLAY_CREDENTIALS) return
    const port = event.ports[0]
    if (!port || !container.controller || event.source !== container.controller) return
    void answerReplayCredentials(port)
  })
}
