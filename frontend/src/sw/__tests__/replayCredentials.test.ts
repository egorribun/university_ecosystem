import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { REQUEST_OFFLINE_REPLAY_CREDENTIALS, requestReplayCredentials } from "../replayCredentials"

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
})
