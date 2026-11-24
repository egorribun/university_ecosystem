import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  REQUEST_OFFLINE_REPLAY_CREDENTIALS,
  REQUEST_OFFLINE_REPLAY_CREDENTIALS_V2,
  requestRefreshedReplayCredentials,
  requestReplayCredentials,
} from "../replayCredentials"

const CREDENTIALS = { csrfToken: "csrf-A", sessionNonce: "session-A" }

/** A controlled window that answers the transferred port with the given payload. */
function answeringClient(answer: unknown) {
  return {
    postMessage: vi.fn((_message: unknown, transfer: MessagePort[]) => {
      transfer[0]?.postMessage(answer)
    }),
  }
}

/** A controlled window that accepts the request but never answers. */
function silentClient() {
  return { postMessage: vi.fn() }
}

function stubClients(clients: unknown) {
  vi.stubGlobal("clients", { matchAll: vi.fn().mockResolvedValue(clients) })
}

describe("AUD-375: service worker asks a controlled window for replay credentials", () => {
  beforeEach(() => {
    vi.useRealTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it("returns the first well-formed answer, requesting it over a transferred port", async () => {
    const client = answeringClient(CREDENTIALS)
    stubClients([client])

    await expect(requestReplayCredentials()).resolves.toEqual(CREDENTIALS)

    expect(client.postMessage).toHaveBeenCalledExactlyOnceWith(
      { type: REQUEST_OFFLINE_REPLAY_CREDENTIALS },
      [expect.any(MessagePort)]
    )
  })

  it("skips a refusal and a malformed answer until a window answers", async () => {
    stubClients([
      answeringClient(null),
      answeringClient({ csrfToken: 7, sessionNonce: "session-A" }),
      answeringClient(CREDENTIALS),
    ])

    await expect(requestReplayCredentials()).resolves.toEqual(CREDENTIALS)
  })

  it.each([
    ["a non-object answer", "credentials"],
    ["a missing answer", null],
    ["an empty token", { csrfToken: "", sessionNonce: "session-A" }],
    ["an oversized token", { csrfToken: "t".repeat(4_097), sessionNonce: "session-A" }],
    ["a non-string token", { csrfToken: 1, sessionNonce: "session-A" }],
    ["a missing token", { sessionNonce: "session-A" }],
    ["an empty nonce", { csrfToken: "csrf-A", sessionNonce: "" }],
    ["an oversized nonce", { csrfToken: "csrf-A", sessionNonce: "n".repeat(129) }],
    ["a non-string nonce", { csrfToken: "csrf-A", sessionNonce: ["session-A"] }],
  ])("rejects %s", async (_label, answer) => {
    stubClients([answeringClient(answer)])

    await expect(requestReplayCredentials()).resolves.toBeNull()
  })

  it("returns null when no window is controlled", async () => {
    stubClients([])

    await expect(requestReplayCredentials()).resolves.toBeNull()
  })

  it("returns null when the worker cannot list its controlled windows", async () => {
    vi.stubGlobal("clients", undefined)

    await expect(requestReplayCredentials()).resolves.toBeNull()
  })

  it("treats a window that cannot receive the request as refused and tries the next one", async () => {
    const brokenClient = {
      postMessage: vi.fn(() => {
        throw new Error("detached")
      }),
    }
    stubClients([brokenClient, answeringClient(CREDENTIALS)])

    await expect(requestReplayCredentials()).resolves.toEqual(CREDENTIALS)
    expect(brokenClient.postMessage).toHaveBeenCalledOnce()
  })

  it("times out a silent window after one second and moves on", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] })
    const silent = silentClient()
    stubClients([silent, answeringClient(CREDENTIALS)])

    const pending = requestReplayCredentials()
    await vi.advanceTimersByTimeAsync(1_000)

    await expect(pending).resolves.toEqual(CREDENTIALS)
    expect(silent.postMessage).toHaveBeenCalledOnce()
  })

  it("resolves null when every controlled window stays silent", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] })
    stubClients([silentClient()])

    const pending = requestReplayCredentials()
    await vi.advanceTimersByTimeAsync(1_000)

    await expect(pending).resolves.toBeNull()
  })

  it("requires a versioned acknowledgment bound to the requested session", async () => {
    const oldWindow = answeringClient(CREDENTIALS)
    const wrongSession = answeringClient({ version: 2, ...CREDENTIALS, sessionNonce: "session-B" })
    const refreshed = answeringClient({ version: 2, ...CREDENTIALS })
    stubClients([oldWindow, wrongSession, refreshed])

    await expect(requestRefreshedReplayCredentials("session-A")).resolves.toEqual(CREDENTIALS)
    expect(refreshed.postMessage).toHaveBeenCalledWith(
      {
        type: REQUEST_OFFLINE_REPLAY_CREDENTIALS_V2,
        version: 2,
        sessionNonce: "session-A",
        expiresAt: expect.any(Number),
      },
      [expect.any(MessagePort)]
    )
  })

  it("allows the bounded bootstrap to finish after the legacy one-second deadline", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] })
    const slowWindow = {
      postMessage: vi.fn((_message: unknown, ports: MessagePort[]) => {
        setTimeout(() => ports[0]?.postMessage({ version: 2, ...CREDENTIALS }), 8_000)
      }),
    }
    stubClients([slowWindow])

    const pending = requestRefreshedReplayCredentials("session-A")
    await vi.advanceTimersByTimeAsync(8_000)

    await expect(pending).resolves.toEqual(CREDENTIALS)
  })

  it("bounds the entire forced request and ignores a late acknowledgment", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] })
    let answer: (() => void) | undefined
    const late = {
      postMessage: vi.fn((_message: unknown, ports: MessagePort[]) => {
        answer = () => ports[0]?.postMessage({ version: 2, ...CREDENTIALS })
      }),
    }
    stubClients([late])

    const pending = requestRefreshedReplayCredentials("session-A")
    await vi.advanceTimersByTimeAsync(9_000)
    await expect(pending).resolves.toBeNull()
    answer?.()
    await vi.runAllTimersAsync()
  })

  it.each(["", "n".repeat(129)])(
    "rejects an invalid forced-refresh session before enumerating windows",
    async (nonce) => {
      const matchAll = vi.fn()
      vi.stubGlobal("clients", { matchAll })

      await expect(requestRefreshedReplayCredentials(nonce)).resolves.toBeNull()
      expect(matchAll).not.toHaveBeenCalled()
    }
  )

  it("bounds a stalled controlled-window enumeration", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] })
    vi.stubGlobal("clients", { matchAll: vi.fn(() => new Promise(() => {})) })

    const pending = requestRefreshedReplayCredentials("session-A")
    await vi.advanceTimersByTimeAsync(9_000)

    await expect(pending).resolves.toBeNull()
  })

  it("does not ask a window when enumeration consumed the refresh deadline", async () => {
    let monotonicNow = performance.now()
    vi.spyOn(performance, "now").mockImplementation(() => monotonicNow)
    const client = answeringClient({ version: 2, ...CREDENTIALS })
    vi.stubGlobal("clients", {
      matchAll: vi.fn(async () => {
        monotonicNow += 9_000
        return [client]
      }),
    })

    await expect(requestRefreshedReplayCredentials("session-A")).resolves.toBeNull()
    expect(client.postMessage).not.toHaveBeenCalled()
  })
})
