import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const ensureCsrfCookie = vi.hoisted(() => vi.fn(async () => undefined))
const forceRefreshCsrfCookie = vi.hoisted(() => vi.fn(async (_signal?: AbortSignal) => true))
vi.mock("@/api/client", () => ({ ensureCsrfCookie }))
vi.mock("@/api/csrfRecovery", () => ({ forceRefreshCsrfCookie }))

import {
  acceptBrowserSessionGeneration,
  getBrowserSessionGeneration,
  rotateBrowserSession,
} from "@/stores/sessionEpoch"
import {
  REQUEST_OFFLINE_REPLAY_CREDENTIALS,
  REQUEST_OFFLINE_REPLAY_CREDENTIALS_V2,
} from "../replayCredentials"
import {
  currentReplaySessionNonce,
  installReplayCredentialResponder,
} from "../replayCredentialResponder"

const GENERATION_KEY = "ecosystem.session.generation.v1"

type Listener = (event: MessageEvent) => void

function fakeContainer(controller: object | null) {
  const listeners: Listener[] = []
  const container = {
    controller,
    addEventListener: vi.fn((type: string, listener: Listener) => {
      if (type === "message") listeners.push(listener)
    }),
  }
  const dispatch = (event: Record<string, unknown>) => {
    for (const listener of listeners) listener(event as unknown as MessageEvent)
  }
  return { container, dispatch }
}

/** Opens a channel and returns the window-side port plus a list of received answers. */
function answerChannel() {
  const channel = new MessageChannel()
  const answers: unknown[] = []
  channel.port1.onmessage = ({ data }) => answers.push(data)
  return { port: channel.port2, answers, close: () => channel.port1.close() }
}

function requestFrom(source: unknown, ports: MessagePort[]): Record<string, unknown> {
  return {
    data: { type: REQUEST_OFFLINE_REPLAY_CREDENTIALS },
    source,
    ports,
  }
}

function refreshedRequestFrom(
  source: unknown,
  ports: MessagePort[],
  sessionNonce: string | null,
  expiresAt = Date.now() + 9_000
): Record<string, unknown> {
  return {
    data: { type: REQUEST_OFFLINE_REPLAY_CREDENTIALS_V2, version: 2, sessionNonce, expiresAt },
    source,
    ports,
  }
}

function setCsrfCookie(value: string) {
  document.cookie = `csrf_token=${value}; path=/`
}

function clearCsrfCookie() {
  document.cookie = "csrf_token=; Max-Age=0; path=/"
}

function verifiedSession() {
  localStorage.clear()
  rotateBrowserSession()
  return getBrowserSessionGeneration()
}

describe("AUD-375: window answers replay credentials only for the live session", () => {
  let controller: object

  beforeEach(() => {
    localStorage.clear()
    clearCsrfCookie()
    acceptBrowserSessionGeneration()
    controller = { state: "activated" }
    ensureCsrfCookie.mockReset()
    ensureCsrfCookie.mockResolvedValue(undefined)
    forceRefreshCsrfCookie.mockReset()
    forceRefreshCsrfCookie.mockResolvedValue(true)
  })

  afterEach(() => {
    vi.useRealTimers()
    clearCsrfCookie()
    localStorage.clear()
    acceptBrowserSessionGeneration()
    vi.restoreAllMocks()
  })

  it("answers the CSRF token and session nonce after ensuring the cookie exists", async () => {
    const nonce = verifiedSession()
    ensureCsrfCookie.mockImplementationOnce(async () => {
      setCsrfCookie("token.after-ensure")
    })
    const { container, dispatch } = fakeContainer(controller)
    installReplayCredentialResponder(container as unknown as ServiceWorkerContainer)
    const channel = answerChannel()

    dispatch(requestFrom(controller, [channel.port]))

    await vi.waitFor(() => expect(channel.answers).toHaveLength(1))
    expect(ensureCsrfCookie).toHaveBeenCalledOnce()
    expect(channel.answers[0]).toEqual({ csrfToken: "token.after-ensure", sessionNonce: nonce })
    channel.close()
  })

  it("refuses when the browser session is not verified against the stored generation", async () => {
    verifiedSession()
    localStorage.setItem(GENERATION_KEY, JSON.stringify({ nonce: "foreign-session", hash: null }))
    setCsrfCookie("token-1")
    const { container, dispatch } = fakeContainer(controller)
    installReplayCredentialResponder(container as unknown as ServiceWorkerContainer)
    const channel = answerChannel()

    dispatch(requestFrom(controller, [channel.port]))

    await vi.waitFor(() => expect(channel.answers).toEqual([null]))
    expect(ensureCsrfCookie).not.toHaveBeenCalled()
    channel.close()
  })

  it("refuses when no session generation has been established", async () => {
    setCsrfCookie("token-1")
    const { container, dispatch } = fakeContainer(controller)
    installReplayCredentialResponder(container as unknown as ServiceWorkerContainer)
    const channel = answerChannel()

    dispatch(requestFrom(controller, [channel.port]))

    await vi.waitFor(() => expect(channel.answers).toEqual([null]))
    channel.close()
  })

  it("refuses when the CSRF cookie is absent even with a live session", async () => {
    verifiedSession()
    clearCsrfCookie()
    const { container, dispatch } = fakeContainer(controller)
    installReplayCredentialResponder(container as unknown as ServiceWorkerContainer)
    const channel = answerChannel()

    dispatch(requestFrom(controller, [channel.port]))

    await vi.waitFor(() => expect(channel.answers).toEqual([null]))
    channel.close()
  })

  it("refuses a malformed percent-encoded CSRF cookie", async () => {
    verifiedSession()
    setCsrfCookie("%E0%A4%A")
    const { container, dispatch } = fakeContainer(controller)
    installReplayCredentialResponder(container as unknown as ServiceWorkerContainer)
    const channel = answerChannel()

    dispatch(requestFrom(controller, [channel.port]))

    await vi.waitFor(() => expect(channel.answers).toEqual([null]))
    channel.close()
  })

  it("decodes an encoded CSRF cookie exactly as the API client reads it", async () => {
    const nonce = verifiedSession()
    setCsrfCookie("a%2Eb")
    const { container, dispatch } = fakeContainer(controller)
    installReplayCredentialResponder(container as unknown as ServiceWorkerContainer)
    const channel = answerChannel()

    dispatch(requestFrom(controller, [channel.port]))

    await vi.waitFor(() => expect(channel.answers).toHaveLength(1))
    expect(channel.answers[0]).toEqual({ csrfToken: "a.b", sessionNonce: nonce })
    channel.close()
  })

  it("refuses when the session changes while the cookie is being ensured", async () => {
    verifiedSession()
    ensureCsrfCookie.mockImplementationOnce(async () => {
      setCsrfCookie("token-1")
      localStorage.setItem(GENERATION_KEY, JSON.stringify({ nonce: "rotated", hash: null }))
    })
    const { container, dispatch } = fakeContainer(controller)
    installReplayCredentialResponder(container as unknown as ServiceWorkerContainer)
    const channel = answerChannel()

    dispatch(requestFrom(controller, [channel.port]))

    await vi.waitFor(() => expect(channel.answers).toEqual([null]))
    channel.close()
  })

  it("ignores messages from anything other than the controlling worker", async () => {
    verifiedSession()
    setCsrfCookie("token-1")
    const { container, dispatch } = fakeContainer(controller)
    installReplayCredentialResponder(container as unknown as ServiceWorkerContainer)
    const foreignChannel = answerChannel()
    const portless = answerChannel()

    dispatch(requestFrom({ state: "other-worker" }, [foreignChannel.port]))
    dispatch(requestFrom(controller, []))
    dispatch({
      data: { type: "PROCESS_OFFLINE_QUEUES" },
      source: controller,
      ports: [portless.port],
    })
    dispatch({ data: null, source: controller, ports: [portless.port] })

    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(foreignChannel.answers).toEqual([])
    expect(portless.answers).toEqual([])
    expect(ensureCsrfCookie).not.toHaveBeenCalled()
    foreignChannel.close()
    portless.close()
  })

  it("ignores a request when no worker controls the page", async () => {
    verifiedSession()
    setCsrfCookie("token-1")
    const { container, dispatch } = fakeContainer(null)
    installReplayCredentialResponder(container as unknown as ServiceWorkerContainer)
    const channel = answerChannel()

    dispatch(requestFrom(controller, [channel.port]))

    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(channel.answers).toEqual([])
    channel.close()
  })

  it("installs one listener per service worker container", () => {
    const { container } = fakeContainer(controller)
    const typed = container as unknown as ServiceWorkerContainer

    installReplayCredentialResponder(typed)
    installReplayCredentialResponder(typed)

    expect(container.addEventListener).toHaveBeenCalledOnce()
  })

  it("exposes the nonce only while the window owns a verified session", () => {
    expect(currentReplaySessionNonce()).toBeNull()

    const nonce = verifiedSession()
    expect(currentReplaySessionNonce()).toBe(nonce)

    localStorage.setItem(GENERATION_KEY, JSON.stringify({ nonce: "foreign-session", hash: null }))
    expect(currentReplaySessionNonce()).toBeNull()
  })

  it("forces bootstrap for the same session before sending a versioned acknowledgment", async () => {
    const nonce = verifiedSession()
    setCsrfCookie("old-token")
    forceRefreshCsrfCookie.mockImplementationOnce(async () => {
      setCsrfCookie("new-token")
      return true
    })
    const { container, dispatch } = fakeContainer(controller)
    installReplayCredentialResponder(container as unknown as ServiceWorkerContainer)
    const channel = answerChannel()

    dispatch(refreshedRequestFrom(controller, [channel.port], nonce))

    await vi.waitFor(() =>
      expect(channel.answers).toEqual([{ version: 2, csrfToken: "new-token", sessionNonce: nonce }])
    )
    expect(forceRefreshCsrfCookie).toHaveBeenCalledOnce()
    expect(ensureCsrfCookie).not.toHaveBeenCalled()
    channel.close()
  })

  it("refuses a forced request for another session before bootstrap", async () => {
    verifiedSession()
    setCsrfCookie("old-token")
    const { container, dispatch } = fakeContainer(controller)
    installReplayCredentialResponder(container as unknown as ServiceWorkerContainer)
    const channel = answerChannel()

    dispatch(refreshedRequestFrom(controller, [channel.port], "other-session"))

    await vi.waitFor(() => expect(channel.answers).toEqual([null]))
    expect(forceRefreshCsrfCookie).not.toHaveBeenCalled()
    channel.close()
  })

  it("ignores a forced request with an unsupported protocol version", async () => {
    const nonce = verifiedSession()
    const { container, dispatch } = fakeContainer(controller)
    installReplayCredentialResponder(container as unknown as ServiceWorkerContainer)
    const channel = answerChannel()

    dispatch({
      data: {
        type: REQUEST_OFFLINE_REPLAY_CREDENTIALS_V2,
        version: 1,
        sessionNonce: nonce,
        expiresAt: Date.now() + 9_000,
      },
      source: controller,
      ports: [channel.port],
    })

    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(channel.answers).toEqual([])
    expect(forceRefreshCsrfCookie).not.toHaveBeenCalled()
    channel.close()
  })

  it("does not start a bootstrap after the worker's request deadline", async () => {
    const nonce = verifiedSession()
    setCsrfCookie("old-token")
    const { container, dispatch } = fakeContainer(controller)
    installReplayCredentialResponder(container as unknown as ServiceWorkerContainer)
    const channel = answerChannel()

    dispatch(refreshedRequestFrom(controller, [channel.port], nonce, Date.now() - 1))

    await vi.waitFor(() => expect(channel.answers).toEqual([null]))
    expect(forceRefreshCsrfCookie).not.toHaveBeenCalled()
    channel.close()
  })

  it.each([undefined, "invalid", NaN, Infinity])(
    "refuses an invalid forced request deadline (%s)",
    async (expiresAt) => {
      const nonce = verifiedSession()
      setCsrfCookie("old-token")
      const { container, dispatch } = fakeContainer(controller)
      installReplayCredentialResponder(container as unknown as ServiceWorkerContainer)
      const channel = answerChannel()

      dispatch({
        data: {
          type: REQUEST_OFFLINE_REPLAY_CREDENTIALS_V2,
          version: 2,
          sessionNonce: nonce,
          expiresAt,
        },
        source: controller,
        ports: [channel.port],
      })

      await vi.waitFor(() => expect(channel.answers).toEqual([null]))
      expect(forceRefreshCsrfCookie).not.toHaveBeenCalled()
      channel.close()
    }
  )

  it("refuses a success that settles after the worker's request deadline", async () => {
    const nonce = verifiedSession()
    setCsrfCookie("old-token")
    let now = Date.now()
    const expiresAt = now + 100
    vi.spyOn(Date, "now").mockImplementation(() => now)
    forceRefreshCsrfCookie.mockImplementationOnce(async () => {
      setCsrfCookie("new-token")
      now = expiresAt + 1
      return true
    })
    const { container, dispatch } = fakeContainer(controller)
    installReplayCredentialResponder(container as unknown as ServiceWorkerContainer)
    const channel = answerChannel()

    dispatch(refreshedRequestFrom(controller, [channel.port], nonce, expiresAt))

    await vi.waitFor(() => expect(channel.answers).toEqual([null]))
    channel.close()
  })

  it("refuses a successful bootstrap that does not provide a cookie", async () => {
    const nonce = verifiedSession()
    clearCsrfCookie()
    const { container, dispatch } = fakeContainer(controller)
    installReplayCredentialResponder(container as unknown as ServiceWorkerContainer)
    const channel = answerChannel()

    dispatch(refreshedRequestFrom(controller, [channel.port], nonce))

    await vi.waitFor(() => expect(channel.answers).toEqual([null]))
    channel.close()
  })

  it.each([false, "throws"])("refuses a failed bootstrap (%s)", async (result) => {
    const nonce = verifiedSession()
    setCsrfCookie("old-token")
    if (result === "throws") forceRefreshCsrfCookie.mockRejectedValueOnce(new Error("unavailable"))
    else forceRefreshCsrfCookie.mockResolvedValueOnce(false)
    const { container, dispatch } = fakeContainer(controller)
    installReplayCredentialResponder(container as unknown as ServiceWorkerContainer)
    const channel = answerChannel()

    dispatch(refreshedRequestFrom(controller, [channel.port], nonce))

    await vi.waitFor(() => expect(channel.answers).toEqual([null]))
    channel.close()
  })

  it.each(["session", "controller"])(
    "refuses when the %s changes during bootstrap",
    async (change) => {
      const nonce = verifiedSession()
      setCsrfCookie("old-token")
      const { container, dispatch } = fakeContainer(controller)
      forceRefreshCsrfCookie.mockImplementationOnce(async () => {
        setCsrfCookie("new-token")
        if (change === "session") rotateBrowserSession()
        else container.controller = null
        return true
      })
      installReplayCredentialResponder(container as unknown as ServiceWorkerContainer)
      const channel = answerChannel()

      dispatch(refreshedRequestFrom(controller, [channel.port], nonce))

      await vi.waitFor(() => expect(channel.answers).toEqual([null]))
      channel.close()
    }
  )

  it("aborts an overdue bootstrap and does not send a late success", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] })
    const nonce = verifiedSession()
    setCsrfCookie("old-token")
    let signal: AbortSignal | undefined
    let release!: (value: boolean) => void
    forceRefreshCsrfCookie.mockImplementationOnce((requestSignal) => {
      signal = requestSignal
      return new Promise((resolve) => {
        release = resolve
      })
    })
    const { container, dispatch } = fakeContainer(controller)
    installReplayCredentialResponder(container as unknown as ServiceWorkerContainer)
    const channel = answerChannel()

    dispatch(refreshedRequestFrom(controller, [channel.port], nonce))
    await vi.advanceTimersByTimeAsync(9_000)
    vi.useRealTimers()
    await vi.waitFor(() => expect(channel.answers).toEqual([null]))
    expect(signal?.aborted).toBe(true)
    release(true)
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(channel.answers).toEqual([null])
    channel.close()
  })
})
