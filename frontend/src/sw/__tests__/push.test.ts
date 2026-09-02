import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { initPushHandlers } from "../push"
import { sanitizeReportPayload, storePendingNavigation, storePendingReport } from "../offline"
import { buildNotificationDetails, parsePushEventData } from "@/push/notification-helpers"

// Mock notification helpers
vi.mock("@/push/notification-helpers", () => ({
  parsePushEventData: vi.fn((data: any) => ({
    body: "Mock Body",
    url: "/mock-url",
    data: { type: data ? data.type : "default" },
  })),
  buildNotificationDetails: vi.fn((payload: any) => ({
    title: "Mock Title",
    options: {
      body: payload.body,
      data: { url: payload.url, type: payload.data?.type },
    },
  })),
}))

// Mock offline storage helpers
vi.mock("../offline", () => ({
  sanitizeReportPayload: vi.fn((val) => val),
  storePendingNavigation: vi.fn(),
  storePendingReport: vi.fn(),
}))

describe("Service Worker - Push Notifications", () => {
  const eventListeners: Record<string, Function> = {}

  let originalAddEventListener: any
  let originalClients: any
  let originalRegistration: any
  let onlineSpy: any

  beforeEach(() => {
    eventListeners.push = undefined as any
    eventListeners.notificationclick = undefined as any

    originalAddEventListener = globalThis.addEventListener
    originalClients = (globalThis as any).clients
    originalRegistration = (globalThis as any).registration

    globalThis.addEventListener = vi.fn((event: string, callback: any) => {
      eventListeners[event] = callback
    }) as any

    const mockClients = {
      matchAll: vi.fn(),
      openWindow: vi.fn(),
    }

    const mockRegistration = {
      showNotification: vi.fn(),
    }

    ;(globalThis as any).clients = mockClients
    ;(globalThis as any).registration = mockRegistration

    onlineSpy = vi.spyOn(navigator, "onLine", "get").mockReturnValue(true)

    initPushHandlers()
  })

  afterEach(() => {
    globalThis.addEventListener = originalAddEventListener
    ;(globalThis as any).clients = originalClients
    ;(globalThis as any).registration = originalRegistration
    if (onlineSpy) {
      onlineSpy.mockRestore()
    }
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  describe("Push Event Handler", () => {
    it("registers push event listener", () => {
      expect(self.addEventListener).toHaveBeenCalledWith("push", expect.any(Function))
      expect(eventListeners.push).toBeDefined()
    })

    it("posts message to visible clients for in-app push type", async () => {
      vi.mocked(buildNotificationDetails).mockReturnValueOnce({
        title: "Mock Title",
        options: {
          body: "Mock Body",
          data: {
            url: "/mock-url",
            type: "in-app",
            notificationId: "018f10c0-0000-7000-8000-000000000001",
            topic: "news.published",
          },
        },
      } as never)
      const mockClient = {
        visibilityState: "visible",
        postMessage: vi.fn(),
      }
      ;((self as any).clients.matchAll as any).mockResolvedValue([mockClient])

      const mockEvent = {
        data: { type: "in-app" },
        waitUntil: vi.fn((promise) => promise),
      }

      await (eventListeners.push as any)(mockEvent)

      expect(mockClient.postMessage).toHaveBeenCalledWith({
        type: "PUSH_NOTIFICATION",
        notificationId: "018f10c0-0000-7000-8000-000000000001",
        topic: "news.published",
        toast: {
          id: "018f10c0-0000-7000-8000-000000000001",
          title: "Mock Title",
          body: "Mock Body",
          url: "/mock-url",
          data: expect.objectContaining({ topic: "news.published" }),
        },
      })
      expect((self as any).registration.showNotification).not.toHaveBeenCalled()
    })

    it("shows system notification if no visible clients or default push type", async () => {
      ;((self as any).clients.matchAll as any).mockResolvedValue([])

      const mockEvent = {
        data: { type: "default" },
        waitUntil: vi.fn((promise) => promise),
      }

      await (eventListeners.push as any)(mockEvent)

      expect((self as any).registration.showNotification).toHaveBeenCalledWith("Mock Title", {
        body: "Mock Body",
        data: { url: "/mock-url", type: "default" },
      })
    })
  })

  describe("Notification Click Event Handler", () => {
    it("registers notificationclick event listener", () => {
      expect(self.addEventListener).toHaveBeenCalledWith("notificationclick", expect.any(Function))
      expect(eventListeners.notificationclick).toBeDefined()
    })

    it("closes the notification and focuses existing window if found", async () => {
      const origin = window.location.origin
      const mockClient = {
        url: `${origin}/mock-url`,
        focus: vi.fn(),
      }
      ;((self as any).clients.matchAll as any).mockResolvedValue([mockClient])

      const mockEvent = {
        notification: {
          close: vi.fn(),
          data: { url: "/mock-url" },
        },
        waitUntil: vi.fn((promise) => promise),
      }

      await (eventListeners.notificationclick as any)(mockEvent)
      await (mockEvent.waitUntil.mock.results[0] as any).value

      expect(mockEvent.notification.close).toHaveBeenCalled()
      expect(mockClient.focus).toHaveBeenCalled()
      expect((self as any).clients.openWindow).not.toHaveBeenCalled()
    })

    it("opens a new window and reports clicks when online", async () => {
      ;((self as any).clients.matchAll as any).mockResolvedValue([])
      const origin = window.location.origin
      const mockClient = { url: `${origin}/mock-url` }
      ;((self as any).clients.openWindow as any).mockResolvedValue(mockClient)

      const fetchMock = vi.fn().mockResolvedValue({ ok: true })
      vi.stubGlobal("fetch", fetchMock)

      const mockEvent = {
        notification: {
          close: vi.fn(),
          data: {
            url: "/mock-url",
            reportUrl: "/api/report-click",
            notificationId: "123",
            reportPayload: { ref: "email" },
          },
        },
        waitUntil: vi.fn((promise) => promise),
      }

      await (eventListeners.notificationclick as any)(mockEvent)
      await (mockEvent.waitUntil.mock.results[0] as any).value

      expect((self as any).clients.openWindow).toHaveBeenCalledWith(`${origin}/mock-url`)
      expect(fetchMock).toHaveBeenCalledWith(`${origin}/api/report-click`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ref: "email", notificationId: "123" }),
        keepalive: true,
      })
    })

    it("opens a window after ignoring non-matching clients", async () => {
      const nonMatchingClient = {
        url: `${window.location.origin}/different`,
        focus: vi.fn(),
      }
      ;((self as any).clients.matchAll as any).mockResolvedValue([nonMatchingClient])
      ;((self as any).clients.openWindow as any).mockResolvedValue({
        url: `${window.location.origin}/mock-url`,
      })

      const mockEvent = {
        notification: { close: vi.fn(), data: { url: "/mock-url" } },
        waitUntil: vi.fn((promise) => promise),
      }

      await (eventListeners.notificationclick as any)(mockEvent)
      await (mockEvent.waitUntil.mock.results[0] as any).value

      expect(nonMatchingClient.focus).not.toHaveBeenCalled()
      expect((self as any).clients.openWindow).toHaveBeenCalledWith(
        `${window.location.origin}/mock-url`
      )
    })

    it.each([
      { navigationSucceeds: false, expectQueuedNavigation: true },
      { navigationSucceeds: true, expectQueuedNavigation: false },
    ])(
      "queues a failed online report when navigation success is $navigationSucceeds",
      async ({ navigationSucceeds, expectQueuedNavigation }) => {
        vi.mocked(storePendingNavigation).mockClear()
        vi.mocked(storePendingReport).mockClear()
        ;((self as any).clients.matchAll as any).mockResolvedValue([])
        ;((self as any).clients.openWindow as any).mockResolvedValue(
          navigationSucceeds ? { url: `${window.location.origin}/mock-url` } : null
        )
        vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline during report")))

        const mockEvent = {
          notification: {
            close: vi.fn(),
            data: {
              url: "/mock-url",
              reportUrl: "/api/report-click",
              notificationId: "without-payload",
            },
          },
          waitUntil: vi.fn((promise) => promise),
        }

        await (eventListeners.notificationclick as any)(mockEvent)
        await (mockEvent.waitUntil.mock.results[0] as any).value

        expect(sanitizeReportPayload).toHaveBeenCalledWith({})
        expect(storePendingReport).toHaveBeenCalledWith({
          url: `${window.location.origin}/mock-url`,
          reportUrl: `${window.location.origin}/api/report-click`,
          timestamp: expect.any(Number),
          payload: { notificationId: "without-payload" },
        })
        if (expectQueuedNavigation) {
          expect(storePendingNavigation).toHaveBeenCalled()
        } else {
          expect(storePendingNavigation).not.toHaveBeenCalled()
        }
      }
    )

    it("enqueues report offline if fetch fails or navigator is offline", async () => {
      ;((self as any).clients.matchAll as any).mockResolvedValue([])
      ;((self as any).clients.openWindow as any).mockResolvedValue(null) // navigation failed

      vi.stubGlobal("self", {
        ...globalThis,
        location: globalThis.location,
        navigator: { onLine: false }, // offline
      })

      const mockEvent = {
        notification: {
          close: vi.fn(),
          data: {
            url: "/mock-url",
            reportUrl: "/api/report-click",
            notificationId: "123",
            reportPayload: { ref: "email" },
          },
        },
        waitUntil: vi.fn((promise) => promise),
      }

      await (eventListeners.notificationclick as any)(mockEvent)
      await (mockEvent.waitUntil.mock.results[0] as any).value

      const origin = window.location.origin
      expect(storePendingNavigation).toHaveBeenCalledWith({
        url: `${origin}/mock-url`,
        timestamp: expect.any(Number),
      })
      expect(storePendingReport).toHaveBeenCalledWith({
        url: `${origin}/mock-url`,
        reportUrl: `${origin}/api/report-click`,
        timestamp: expect.any(Number),
        payload: { ref: "email", notificationId: "123" },
      })
    })

    it("uses payload and notification option fallbacks for an in-app toast", async () => {
      vi.mocked(parsePushEventData).mockReturnValue({
        body: "",
        url: "",
        data: { type: "in-app" },
      } as never)
      vi.mocked(buildNotificationDetails).mockReturnValue({
        title: "Fallback title",
        options: { body: "", data: { url: "/fallback-url" } },
      } as never)

      const mockClient = {
        visibilityState: "visible",
        postMessage: vi.fn(),
      }
      ;((self as any).clients.matchAll as any).mockResolvedValue([mockClient])

      const mockEvent = {
        data: { type: "in-app" },
        waitUntil: vi.fn((promise) => promise),
      }

      await (eventListeners.push as any)(mockEvent)

      expect(mockClient.postMessage).toHaveBeenCalledWith({
        type: "PUSH_NOTIFICATION",
        toast: { title: "Fallback title", body: "", url: "/fallback-url" },
      })
    })

    it("queues navigation when a click has no report URL and opening fails", async () => {
      vi.mocked(storePendingNavigation).mockClear()
      ;((self as any).clients.matchAll as any).mockResolvedValue([])
      ;((self as any).clients.openWindow as any).mockResolvedValue(null)

      const mockEvent = {
        notification: {
          close: vi.fn(),
          data: { url: "/without-report" },
        },
        waitUntil: vi.fn((promise) => promise),
      }

      await (eventListeners.notificationclick as any)(mockEvent)
      await (mockEvent.waitUntil.mock.results[0] as any).value

      expect(storePendingNavigation).toHaveBeenCalledWith({
        url: `${window.location.origin}/without-report`,
        timestamp: expect.any(Number),
      })
    })

    it("uses the root URL when an in-app push has no URL in either payload", async () => {
      vi.mocked(parsePushEventData).mockReturnValue({
        body: "",
        url: "",
        data: { type: "in-app" },
      } as never)
      vi.mocked(buildNotificationDetails).mockReturnValue({
        title: "Root fallback",
        options: { body: "", data: {} },
      } as never)
      const mockClient = { visibilityState: "visible", postMessage: vi.fn() }
      ;((self as any).clients.matchAll as any).mockResolvedValue([mockClient])

      const mockEvent = {
        data: { type: "in-app" },
        waitUntil: vi.fn((promise) => promise),
      }
      await (eventListeners.push as any)(mockEvent)

      expect(mockClient.postMessage).toHaveBeenCalledWith({
        type: "PUSH_NOTIFICATION",
        toast: { title: "Root fallback", body: "", url: "/" },
      })
    })

    it("uses an empty metadata object when notification options omit data", async () => {
      vi.mocked(parsePushEventData).mockReturnValue({
        body: "Fallback body",
        url: "/payload-url",
        data: { type: "in-app" },
      } as never)
      vi.mocked(buildNotificationDetails).mockReturnValue({
        title: "No option data",
        options: { body: "Fallback body" },
      } as never)
      const mockClient = { visibilityState: "visible", postMessage: vi.fn() }
      ;((self as any).clients.matchAll as any).mockResolvedValue([mockClient])
      const mockEvent = {
        data: { type: "in-app" },
        waitUntil: vi.fn((promise) => promise),
      }

      await (eventListeners.push as any)(mockEvent)

      expect(mockClient.postMessage).toHaveBeenCalledWith({
        type: "PUSH_NOTIFICATION",
        toast: { title: "No option data", body: "Fallback body", url: "/payload-url" },
      })
    })

    it("queues the root navigation when a click has no URL", async () => {
      vi.mocked(storePendingNavigation).mockClear()
      ;((self as any).clients.matchAll as any).mockResolvedValue([])
      ;((self as any).clients.openWindow as any).mockResolvedValue(null)

      const mockEvent = {
        notification: { close: vi.fn(), data: {} },
        waitUntil: vi.fn((promise) => promise),
      }
      await (eventListeners.notificationclick as any)(mockEvent)
      await (mockEvent.waitUntil.mock.results[0] as any).value

      expect(storePendingNavigation).toHaveBeenCalledWith({
        url: `${window.location.origin}/`,
        timestamp: expect.any(Number),
      })
    })

    it("does not report to a cross-origin endpoint", async () => {
      const fetchMock = vi.fn()
      vi.stubGlobal("fetch", fetchMock)
      ;((self as any).clients.matchAll as any).mockResolvedValue([])
      ;((self as any).clients.openWindow as any).mockResolvedValue({
        url: `${window.location.origin}/safe`,
      })
      const mockEvent = {
        notification: {
          close: vi.fn(),
          data: {
            url: "/safe",
            reportUrl: "https://evil.example/collect",
            notificationId: "safe-id",
          },
        },
        waitUntil: vi.fn((promise) => promise),
      }

      await (eventListeners.notificationclick as any)(mockEvent)
      await (mockEvent.waitUntil.mock.results[0] as any).value

      expect(fetchMock).not.toHaveBeenCalled()
      expect(storePendingReport).not.toHaveBeenCalled()
    })

    it("queues navigation when an unsafe report URL and window opening both fail", async () => {
      vi.mocked(storePendingNavigation).mockClear()
      ;((self as any).clients.matchAll as any).mockResolvedValue([])
      ;((self as any).clients.openWindow as any).mockResolvedValue(null)
      const mockEvent = {
        notification: {
          close: vi.fn(),
          data: {
            url: "/safe",
            reportUrl: "https://evil.example/collect",
          },
        },
        waitUntil: vi.fn((promise) => promise),
      }

      await (eventListeners.notificationclick as any)(mockEvent)
      await (mockEvent.waitUntil.mock.results[0] as any).value

      expect(storePendingNavigation).toHaveBeenCalledWith({
        url: `${window.location.origin}/safe`,
        timestamp: expect.any(Number),
      })
      expect(storePendingReport).not.toHaveBeenCalled()
    })

    it("drops non-object report payloads while preserving the notification id", async () => {
      vi.mocked(storePendingReport).mockClear()
      vi.mocked(sanitizeReportPayload).mockReturnValueOnce("unsafe" as never)
      ;((self as any).clients.matchAll as any).mockResolvedValue([])
      ;((self as any).clients.openWindow as any).mockResolvedValue(null)
      vi.stubGlobal("self", {
        ...globalThis,
        location: globalThis.location,
        navigator: { onLine: false },
      })

      const mockEvent = {
        notification: {
          close: vi.fn(),
          data: {
            url: "/mock-url",
            reportUrl: "/api/report-click",
            notificationId: "primitive-payload",
            reportPayload: { ignored: true },
          },
        },
        waitUntil: vi.fn((promise) => promise),
      }
      await (eventListeners.notificationclick as any)(mockEvent)
      await (mockEvent.waitUntil.mock.results[0] as any).value

      expect(storePendingReport).toHaveBeenCalledWith({
        url: `${window.location.origin}/mock-url`,
        reportUrl: `${window.location.origin}/api/report-click`,
        timestamp: expect.any(Number),
        payload: { notificationId: "primitive-payload" },
      })
    })
  })
})
