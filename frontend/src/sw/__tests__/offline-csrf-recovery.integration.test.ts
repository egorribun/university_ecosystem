import { IDBFactory } from "fake-indexeddb"
import { afterEach, describe, expect, it, vi } from "vitest"

vi.mock("@/api/client", () => ({ ensureCsrfCookie: vi.fn(async () => undefined) }))
vi.mock("@/api/csrfRecovery", () => ({
  CSRF_REJECTED_HEADER: "x-csrf-rejected",
  forceRefreshCsrfCookie: vi.fn(async () => {
    document.cookie = "csrf_token=csrf-after; path=/"
    return true
  }),
}))
vi.mock("../logger", () => ({ log: vi.fn(), warn: vi.fn(), error: vi.fn() }))

import { getBrowserSessionGeneration, rotateBrowserSession } from "@/stores/sessionEpoch"
import {
  initOfflineQueue,
  processOfflineQueues,
  readPendingMutations,
  storePendingMutation,
} from "../offline"
import { installReplayCredentialResponder } from "../replayCredentialResponder"

describe("offline CSRF recovery protocol", () => {
  afterEach(() => {
    document.cookie = "csrf_token=; Max-Age=0; path=/"
    localStorage.clear()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it("uses the real window responder to refresh and replay a session-bound queued write", async () => {
    vi.stubGlobal("indexedDB", new IDBFactory())
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(true)
    localStorage.clear()
    rotateBrowserSession()
    const sessionNonce = getBrowserSessionGeneration()
    expect(sessionNonce).toEqual(expect.any(String))
    document.cookie = "csrf_token=csrf-before; path=/"
    await initOfflineQueue()

    const controller = { state: "activated" }
    let listener!: (event: MessageEvent) => void
    const container = {
      controller,
      addEventListener: (_type: string, callback: (event: MessageEvent) => void) => {
        listener = callback
      },
    }
    installReplayCredentialResponder(container as unknown as ServiceWorkerContainer)
    vi.stubGlobal("clients", {
      matchAll: vi.fn().mockResolvedValue([
        {
          postMessage: (data: unknown, ports: MessagePort[]) => {
            listener({ data, ports, source: controller } as unknown as MessageEvent)
          },
        },
      ]),
    })
    await storePendingMutation({
      url: "/api/v1/profile",
      method: "PATCH",
      payload: { displayName: "queued" },
      mutationId: "queued-operation",
      idempotencyKey: "queued-key",
      timestamp: Date.now(),
      sessionNonce,
    })
    const tokens: Array<string | null> = []
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
        tokens.push(new Headers(init?.headers).get("X-CSRF-Token"))
        if (tokens.length > 1) return new Response(null, { status: 204 })
        const denied = new Response(null, { status: 403, headers: { "X-CSRF-Rejected": "1" } })
        Object.defineProperty(denied, "url", {
          value: new URL("/api/v1/profile", window.location.origin).href,
        })
        return denied
      })
    )

    await processOfflineQueues()

    expect(tokens).toEqual(["csrf-before", "csrf-after"])
    expect(await readPendingMutations()).toEqual([])
  })
})
