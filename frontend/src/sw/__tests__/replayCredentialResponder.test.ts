import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const ensureCsrfCookie = vi.hoisted(() => vi.fn(async () => undefined))
vi.mock("@/api/client", () => ({ ensureCsrfCookie }))

import {
  acceptBrowserSessionGeneration,
  getBrowserSessionGeneration,
  rotateBrowserSession,
} from "@/stores/sessionEpoch"
import { REQUEST_OFFLINE_REPLAY_CREDENTIALS } from "../replayCredentials"
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
  })

  afterEach(() => {
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
})
