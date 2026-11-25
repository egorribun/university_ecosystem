import { ensureCsrfCookie } from "@/api/client"
import { forceRefreshCsrfCookie } from "@/api/csrfRecovery"
import { getBrowserSessionGeneration, isCurrentBrowserSession } from "@/stores/sessionEpoch"
import {
  REPLAY_REFRESH_RESPONSE_TIMEOUT_MS,
  REQUEST_OFFLINE_REPLAY_CREDENTIALS,
  REQUEST_OFFLINE_REPLAY_CREDENTIALS_V2,
} from "./replayCredentials"

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

async function answerRefreshedReplayCredentials(
  port: MessagePort,
  expectedSession: unknown,
  expiresAt: unknown,
  stillControlled: () => boolean
): Promise<void> {
  const originalSession = currentReplaySessionNonce()
  const remaining = typeof expiresAt === "number" ? expiresAt - Date.now() : NaN
  if (
    !originalSession ||
    expectedSession !== originalSession ||
    !stillControlled() ||
    !Number.isFinite(remaining) ||
    remaining <= 0
  ) {
    port.postMessage(null)
    return
  }

  const controller = new AbortController()
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    const refreshed = await Promise.race([
      forceRefreshCsrfCookie(controller.signal),
      new Promise<false>((resolve) => {
        timer = setTimeout(
          () => {
            controller.abort()
            resolve(false)
          },
          Math.min(remaining, REPLAY_REFRESH_RESPONSE_TIMEOUT_MS)
        )
      }),
    ])
    const sessionNonce = currentReplaySessionNonce()
    const csrfToken =
      sessionNonce === originalSession && stillControlled() ? readCsrfCookie() : null
    port.postMessage(
      refreshed &&
        !controller.signal.aborted &&
        typeof expiresAt === "number" &&
        Date.now() < expiresAt &&
        sessionNonce &&
        csrfToken
        ? { version: 2, csrfToken, sessionNonce }
        : null
    )
  } catch {
    port.postMessage(null)
  } finally {
    clearTimeout(timer)
  }
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
    const type = event.data?.type
    if (
      type !== REQUEST_OFFLINE_REPLAY_CREDENTIALS &&
      type !== REQUEST_OFFLINE_REPLAY_CREDENTIALS_V2
    )
      return
    const port = event.ports[0]
    if (!port || !container.controller || event.source !== container.controller) return
    if (type === REQUEST_OFFLINE_REPLAY_CREDENTIALS) {
      void answerReplayCredentials(port)
    } else if (event.data?.version === 2) {
      const requestingWorker = container.controller
      void answerRefreshedReplayCredentials(
        port,
        event.data.sessionNonce,
        event.data.expiresAt,
        () => container.controller === requestingWorker
      )
    }
  })
}
