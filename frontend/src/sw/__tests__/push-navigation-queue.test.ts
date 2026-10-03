import { IDBFactory } from "fake-indexeddb"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { initPushHandlers } from "../push"
import { processPendingNavigations, readPendingNavigations, readPendingReports } from "../offline"

vi.mock("../logger", () => ({ log: vi.fn(), warn: vi.fn() }))

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
  "queues one navigation per click when opening fails and report failure is %s",
  async (reportFails) => {
    const clients = {
      matchAll: vi.fn().mockResolvedValue([]),
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
    expect(await readPendingNavigations()).toEqual([{ id: 1, url, timestamp: 123_456 }])
    const reports = await readPendingReports()
    expect(reports).toHaveLength(reportFails ? 1 : 0)
    if (reportFails) {
      expect(reports[0]).toMatchObject({
        url,
        reportUrl: `${location.origin}/api/v1/notifications/click`,
        payload: { notificationId: "queued-click" },
      })
    }

    clients.openWindow.mockClear()
    clients.openWindow.mockResolvedValue({})
    await processPendingNavigations()

    expect(clients.openWindow).toHaveBeenCalledExactlyOnceWith(url)
    expect(await readPendingNavigations()).toEqual([])
  }
)
