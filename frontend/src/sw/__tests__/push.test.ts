/* eslint-disable @typescript-eslint/no-explicit-any */
/* eslint-disable @typescript-eslint/no-unsafe-function-type */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { initPushHandlers } from "../push"
import { storePendingNavigation, storePendingReport } from "../offline"

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
        toast: {
          title: "Mock Title",
          body: "Mock Body",
          url: "/mock-url",
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
  })
})
