import { IDBFactory } from "fake-indexeddb"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { initPushHandlers } from "../push"
import { processPendingNavigations, readPendingNavigations, readPendingReports } from "../offline"

vi.mock("../logger", () => ({ log: vi.fn(), warn: vi.fn() }))

const QUEUE_SESSION = "session-queue"

/** A controlled window answering the replay-credential request with the given answer. */
function windowAnswering(answer: unknown) {
  return {
    postMessage: vi.fn((_message: unknown, transfer: MessagePort[]) => {
      transfer[0]?.postMessage(answer)
    }),
  }
}

beforeEach(() => {
  vi.stubGlobal("indexedDB", new IDBFactory())
  vi.spyOn(navigator, "onLine", "get").mockReturnValue(true)
  vi.spyOn(Date, "now").mockReturnValue(123_456)
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

it.each([false, true])(
  "queues one navigation per failed click, bound to the answering session; report failure is %s",
  async (reportFails) => {
    const clients = {
      matchAll: vi
        .fn()
        .mockResolvedValue([
          windowAnswering({ csrfToken: "csrf-queue", sessionNonce: QUEUE_SESSION }),
        ]),
      openWindow: vi.fn().mockResolvedValue(null),
    }
    vi.stubGlobal("clients", clients)
    const fetchMock = reportFails
      ? vi.fn().mockRejectedValue(new TypeError("network unavailable"))
      : vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal("fetch", fetchMock)
    const listenerSpy = vi.spyOn(globalThis, "addEventListener").mockImplementation(() => {})
    initPushHandlers()
    const listener = listenerSpy.mock.calls.find(([type]) => type === "notificationclick")?.[1]
    if (typeof listener !== "function") throw new Error("missing notificationclick handler")
    const event = {
      notification: {
        close: vi.fn(),
        data: {
          url: "/news/queued",
          reportUrl: "/api/v1/notifications/click",
          notificationId: "queued-click",
        },
      },
      waitUntil: vi.fn<(promise: Promise<void>) => void>(),
    }

    listener(event as unknown as Event)
    expect(event.waitUntil).toHaveBeenCalledExactlyOnceWith(expect.any(Promise))
    await event.waitUntil.mock.calls[0]?.[0]

    const url = `${location.origin}/news/queued`
    expect(await readPendingNavigations()).toEqual([
      { id: 1, url, timestamp: 123_456, sessionNonce: QUEUE_SESSION },
    ])
    const reports = await readPendingReports()
    expect(reports).toHaveLength(reportFails ? 1 : 0)
    if (reportFails) {
      expect(reports[0]).toMatchObject({
        url,
        reportUrl: `${location.origin}/api/v1/notifications/click`,
        payload: { notificationId: "queued-click" },
        sessionNonce: QUEUE_SESSION,
      })
    }

    expect(clients.openWindow).toHaveBeenCalledExactlyOnceWith(url)
    clients.openWindow.mockClear()
    clients.openWindow.mockResolvedValue({})
    // The window no longer vouches for the session, so the bound records must stay queued.
    clients.matchAll.mockResolvedValue([windowAnswering(null)])
    await processPendingNavigations()

    expect(clients.openWindow).not.toHaveBeenCalled()
    // The click POST itself was attempted once; the refused replay pass attempted nothing more.
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(await readPendingNavigations()).toEqual([
      { id: 1, url, timestamp: 123_456, sessionNonce: QUEUE_SESSION },
    ])
    expect(await readPendingReports()).toEqual(reports)
  }
)
