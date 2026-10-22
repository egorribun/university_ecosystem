import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { initPushHandlers } from "../push"
import { sanitizeReportPayload, storePendingNavigation, storePendingReport } from "../offline"
import {
  buildNotificationDetails,
  parsePushEventData,
  type NotificationData,
} from "@/push/notification-helpers"

// Mock notification helpers while keeping the localized generic defaults available.
vi.mock("@/push/notification-helpers", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/push/notification-helpers")>()
  return {
    ...actual,
    parsePushEventData: vi.fn((data: any) => ({
      body: "Mock Body",
      url: "/mock-url",
      data: {
        type: data ? data.type : "default",
        ...(typeof data?.recipientUserId === "string"
          ? { recipientUserId: data.recipientUserId }
          : {}),
      },
    })),
    buildNotificationDetails: vi.fn((payload: any) => {
      const data = {
        url: payload.url,
        type: payload.data?.type,
        ...(typeof payload.data?.recipientUserId === "string"
          ? { recipientUserId: payload.data.recipientUserId }
          : {}),
      }
      return { title: "Mock Title", options: { body: payload.body, data }, data }
    }),
  }
})

const notificationDetails = (title: string, body: string, data: NotificationData) => ({
  title,
  options: { body, data },
  data,
})

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
    vi.mocked(parsePushEventData).mockReset()
    vi.mocked(buildNotificationDetails).mockReset()
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
      vi.mocked(buildNotificationDetails).mockReturnValueOnce(
        notificationDetails("Mock Title", "Mock Body", {
          url: "/mock-url",
          type: "in-app",
          notificationId: "018f10c0-0000-7000-8000-000000000001",
          recipientUserId: "00000000-0000-4000-8000-000000000001",
          topic: "news.published",
        })
      )
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
      expect(mockEvent.waitUntil).toHaveBeenCalledExactlyOnceWith(expect.any(Promise))
      await mockEvent.waitUntil.mock.calls[0]?.[0]

      expect(mockClient.postMessage).toHaveBeenCalledWith({
        type: "PUSH_NOTIFICATION",
        notificationId: "018f10c0-0000-7000-8000-000000000001",
        recipientUserId: "00000000-0000-4000-8000-000000000001",
        topic: "news.published",
        toast: {
          id: "018f10c0-0000-7000-8000-000000000001",
          title: "Mock Title",
          body: "Mock Body",
          url: "/mock-url",
          data: expect.objectContaining({
            topic: "news.published",
            recipientUserId: "00000000-0000-4000-8000-000000000001",
          }),
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
      expect(mockEvent.waitUntil).toHaveBeenCalledExactlyOnceWith(expect.any(Promise))
      await mockEvent.waitUntil.mock.calls[0]?.[0]

      expect((self as any).registration.showNotification).toHaveBeenCalledWith("Mock Title", {
        body: "Mock Body",
        data: { url: "/mock-url", type: "default" },
      })
    })

    const deliveryCases: Array<{
      scenario: string
      type: "in-app" | "default"
      visibility: Array<"visible" | "hidden">
      recipients: number[]
      systemNotifications: number
      recipientUserId: string | undefined
    }> = [
      {
        scenario: "delivers in-app messages only to the visible windows",
        type: "in-app",
        visibility: ["visible", "hidden", "visible"],
        recipients: [0, 2],
        systemNotifications: 0,
        recipientUserId: undefined,
      },
      {
        scenario: "shows a system notification when every window is hidden",
        type: "in-app",
        visibility: ["hidden", "hidden"],
        recipients: [],
        systemNotifications: 1,
        recipientUserId: "00000000-0000-4000-8000-000000000001",
      },
      {
        scenario: "keeps default pushes as system notifications with a visible window",
        type: "default",
        visibility: ["visible", "hidden"],
        recipients: [],
        systemNotifications: 1,
        recipientUserId: undefined,
      },
    ]
    it.each(deliveryCases)(
      "$scenario",
      async ({ type, visibility, recipients, systemNotifications, recipientUserId }) => {
        const clients = visibility.map((visibilityState) => ({
          visibilityState,
          postMessage: vi.fn(),
        }))
        ;((self as any).clients.matchAll as any).mockResolvedValue(clients)
        if (recipientUserId) {
          vi.stubGlobal(
            "fetch",
            vi.fn().mockResolvedValue({
              ok: true,
              status: 200,
              json: async () => ({ id: recipientUserId }),
            })
          )
        }
        const event = {
          data: { type, ...(recipientUserId ? { recipientUserId } : {}) },
          waitUntil: vi.fn<(promise: Promise<void>) => void>(),
        }

        eventListeners.push?.(event)
        expect(event.waitUntil).toHaveBeenCalledExactlyOnceWith(expect.any(Promise))
        await event.waitUntil.mock.calls[0]?.[0]

        expect((self as any).clients.matchAll).toHaveBeenCalledExactlyOnceWith({
          type: "window",
          includeUncontrolled: true,
        })
        for (const [index, client] of clients.entries()) {
          if (recipients.includes(index)) {
            expect(client.postMessage).toHaveBeenCalledExactlyOnceWith({
              type: "PUSH_NOTIFICATION",
              toast: { title: "Mock Title", body: "Mock Body", url: "/mock-url" },
            })
          } else {
            expect(client.postMessage).not.toHaveBeenCalled()
          }
        }
        expect((self as any).registration.showNotification).toHaveBeenCalledTimes(
          systemNotifications
        )
        if (systemNotifications) {
          expect((self as any).registration.showNotification).toHaveBeenCalledWith("Mock Title", {
            body: "Mock Body",
            data: {
              url: "/mock-url",
              type,
              ...(recipientUserId ? { recipientUserId } : {}),
            },
          })
        }
      }
    )

    it("shows a topic-only public broadcast without probing the browser account", async () => {
      const helpers = await vi.importActual<typeof import("@/push/notification-helpers")>(
        "@/push/notification-helpers"
      )
      vi.mocked(parsePushEventData).mockImplementationOnce(helpers.parsePushEventData)
      vi.mocked(buildNotificationDetails).mockImplementationOnce(helpers.buildNotificationDetails)
      const fetchMock = vi.fn()
      vi.stubGlobal("fetch", fetchMock)
      ;((self as any).clients.matchAll as any).mockResolvedValue([])
      const payload = {
        title: "Campus update",
        body: "A public update was published.",
        data: { topic: "news.published" },
      }
      const event = {
        data: {
          json: () => payload,
          text: () => "",
        },
        waitUntil: vi.fn<(promise: Promise<void>) => void>(),
      }

      eventListeners.push?.(event)
      await event.waitUntil.mock.calls[0]?.[0]

      const details = helpers.buildNotificationDetails(payload)
      expect(fetchMock).not.toHaveBeenCalled()
      expect((self as any).registration.showNotification).toHaveBeenCalledExactlyOnceWith(
        details.title,
        details.options
      )
    })

    it.each([
      {
        label: "notification ID only",
        payloadData: {},
        notificationData: { notificationId: "private-notification-id" },
      },
      {
        label: "non-default type only",
        payloadData: { type: "schedule.changed" },
        notificationData: { type: "schedule.changed" },
      },
    ])(
      "suppresses recipientless private content marked by $label",
      async ({ payloadData, notificationData }) => {
        ;((self as any).clients.matchAll as any).mockResolvedValue([])
        vi.mocked(parsePushEventData).mockReturnValueOnce({ data: payloadData } as any)
        vi.mocked(buildNotificationDetails).mockReturnValueOnce(
          notificationDetails("Private title", "Private body", {
            url: "/private-message/123",
            ...notificationData,
          })
        )
        const fetchMock = vi.fn()
        vi.stubGlobal("fetch", fetchMock)
        const event = {
          data: { type: "default" },
          waitUntil: vi.fn<(promise: Promise<void>) => void>(),
        }

        eventListeners.push?.(event)
        await event.waitUntil.mock.calls[0]?.[0]

        expect(fetchMock).not.toHaveBeenCalled()
        expect((self as any).registration.showNotification).not.toHaveBeenCalled()
      }
    )
    it("confirms the recipient before showing a targeted native preview", async () => {
      const recipientUserId = "00000000-0000-4000-8000-000000000001"
      ;((self as any).clients.matchAll as any).mockResolvedValue([])
      vi.mocked(parsePushEventData).mockReturnValueOnce({
        data: { type: "news.published" },
      } as any)
      vi.mocked(buildNotificationDetails).mockReturnValueOnce(
        notificationDetails("Private title", "Private body", {
          url: "/private-message/123",
          type: "news.published",
          recipientUserId,
          notificationId: "018f10c0-0000-7000-8000-000000000002",
        })
      )
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ id: recipientUserId }),
      })
      vi.stubGlobal("fetch", fetchMock)
      const event = {
        data: { type: "news.published" },
        waitUntil: vi.fn<(promise: Promise<void>) => void>(),
      }

      eventListeners.push?.(event)
      await event.waitUntil.mock.calls[0]?.[0]

      expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
        new URL("/api/v1/users/me", self.location.origin),
        expect.objectContaining({
          method: "GET",
          credentials: "include",
          cache: "no-store",
          headers: { Accept: "application/json", "Cache-Control": "no-store" },
          signal: expect.any(AbortSignal),
        })
      )
      expect((self as any).registration.showNotification).toHaveBeenCalledExactlyOnceWith(
        "Private title",
        expect.objectContaining({
          body: "Private body",
          data: expect.objectContaining({
            url: "/private-message/123",
            recipientUserId,
          }),
        })
      )
    })

    it.each([
      {
        scenario: "a different confirmed account",
        response: {
          ok: true,
          status: 200,
          json: async () => ({ id: "00000000-0000-4000-8000-000000000002" }),
        },
      },
      {
        scenario: "an unauthenticated session",
        response: { ok: false, status: 401, json: async () => ({}) },
      },
      {
        scenario: "an authorization refusal",
        response: { ok: false, status: 403, json: async () => ({}) },
      },
    ])("suppresses native private content for $scenario", async ({ response }) => {
      ;((self as any).clients.matchAll as any).mockResolvedValue([])
      vi.mocked(parsePushEventData).mockReturnValueOnce({
        data: { type: "news.published" },
      } as any)
      vi.mocked(buildNotificationDetails).mockReturnValueOnce(
        notificationDetails("Private title", "Private body", {
          type: "news.published",
          recipientUserId: "00000000-0000-4000-8000-000000000001",
          notificationId: "private-notification-id",
          url: "/private-message/123",
        })
      )
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response))
      const event = {
        data: { type: "news.published" },
        waitUntil: vi.fn<(promise: Promise<void>) => void>(),
      }

      eventListeners.push?.(event)
      await event.waitUntil.mock.calls[0]?.[0]

      expect((self as any).registration.showNotification).not.toHaveBeenCalled()
    })

    it("suppresses a native private notification with no valid recipient", async () => {
      ;((self as any).clients.matchAll as any).mockResolvedValue([])
      vi.mocked(parsePushEventData).mockReturnValueOnce({
        data: { type: "news.published" },
      } as any)
      vi.mocked(buildNotificationDetails).mockReturnValueOnce(
        notificationDetails("Private title", "Private body", {
          type: "news.published",
          notificationId: "private-notification-id",
          url: "/private-message/123",
        })
      )
      const fetchMock = vi.fn()
      vi.stubGlobal("fetch", fetchMock)
      const event = {
        data: { type: "news.published" },
        waitUntil: vi.fn<(promise: Promise<void>) => void>(),
      }

      eventListeners.push?.(event)
      await event.waitUntil.mock.calls[0]?.[0]

      expect(fetchMock).not.toHaveBeenCalled()
      expect((self as any).registration.showNotification).not.toHaveBeenCalled()
    })

    it.each([
      {
        scenario: "the session endpoint is unavailable",
        setupFetch: () => vi.fn().mockRejectedValue(new Error("offline")),
      },
      {
        scenario: "the session endpoint returns a server error",
        setupFetch: () => vi.fn().mockResolvedValue({ ok: false, status: 503 }),
      },
      {
        scenario: "the session response is malformed",
        setupFetch: () =>
          vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ id: "bad" }) }),
      },
      {
        scenario: "the session response contains malformed JSON",
        setupFetch: () =>
          vi.fn().mockResolvedValue({
            ok: true,
            status: 200,
            json: async () => {
              throw new SyntaxError("invalid JSON")
            },
          }),
      },
    ])("uses a generic privacy-safe native notification when $scenario", async ({ setupFetch }) => {
      const recipientUserId = "00000000-0000-4000-8000-000000000001"
      ;((self as any).clients.matchAll as any).mockResolvedValue([])
      vi.mocked(parsePushEventData).mockReturnValueOnce({
        data: { type: "schedule.changed" },
      } as any)
      vi.mocked(buildNotificationDetails).mockReturnValueOnce(
        notificationDetails("Private title", "Private body", {
          type: "schedule.changed",
          recipientUserId,
          notificationId: "private-notification-id",
          url: "/private-message/123",
        })
      )
      vi.stubGlobal("fetch", setupFetch())
      const event = {
        data: { type: "schedule.changed" },
        waitUntil: vi.fn<(promise: Promise<void>) => void>(),
      }
      const helpers = await vi.importActual<typeof import("@/push/notification-helpers")>(
        "@/push/notification-helpers"
      )

      eventListeners.push?.(event)
      await event.waitUntil.mock.calls[0]?.[0]

      expect((self as any).registration.showNotification).toHaveBeenCalledExactlyOnceWith(
        helpers.getDefaultNotificationTitle(),
        {
          body: helpers.getDefaultNotificationBody(),
          icon: helpers.DEFAULT_ICON,
          badge: helpers.DEFAULT_ICON,
          data: { url: "/" },
        }
      )
      expect(
        JSON.stringify((self as any).registration.showNotification.mock.calls[0])
      ).not.toContain("Private")
      expect(
        JSON.stringify((self as any).registration.showNotification.mock.calls[0])
      ).not.toContain(recipientUserId)
    })

    it("uses a generic privacy-safe notification when the session request times out", async () => {
      vi.useFakeTimers()
      try {
        const recipientUserId = "00000000-0000-4000-8000-000000000001"
        ;((self as any).clients.matchAll as any).mockResolvedValue([])
        vi.mocked(parsePushEventData).mockReturnValueOnce({
          data: { type: "schedule.changed" },
        } as any)
        vi.mocked(buildNotificationDetails).mockReturnValueOnce(
          notificationDetails("Private title", "Private body", {
            type: "schedule.changed",
            recipientUserId,
            notificationId: "private-notification-id",
            url: "/private-message/123",
          })
        )
        let requestSignal: AbortSignal | null | undefined
        const fetchMock = vi.fn<typeof fetch>(
          (_input, init) =>
            new Promise<Response>((_, reject) => {
              requestSignal = init?.signal
              requestSignal?.addEventListener(
                "abort",
                () => reject(new Error("session request aborted")),
                { once: true }
              )
            })
        )
        vi.stubGlobal("fetch", fetchMock)
        const event = {
          data: { type: "schedule.changed" },
          waitUntil: vi.fn<(promise: Promise<void>) => void>(),
        }

        ;(eventListeners.push as any)(event)
        const handling = event.waitUntil.mock.calls[0]?.[0]
        expect(handling).toBeDefined()
        await Promise.resolve()
        expect(fetchMock).toHaveBeenCalledExactlyOnceWith(
          new URL("/api/v1/users/me", self.location.origin),
          expect.objectContaining({ signal: expect.any(AbortSignal) })
        )

        await vi.advanceTimersByTimeAsync(2_000)
        await handling

        expect(requestSignal?.aborted).toBe(true)
        const helpers = await vi.importActual<typeof import("@/push/notification-helpers")>(
          "@/push/notification-helpers"
        )
        expect((self as any).registration.showNotification).toHaveBeenCalledExactlyOnceWith(
          helpers.getDefaultNotificationTitle(),
          {
            body: helpers.getDefaultNotificationBody(),
            icon: helpers.DEFAULT_ICON,
            badge: helpers.DEFAULT_ICON,
            data: { url: "/" },
          }
        )
      } finally {
        vi.useRealTimers()
      }
    })
    it("uses a generic native notification without probing when the worker is offline", async () => {
      const recipientUserId = "00000000-0000-4000-8000-000000000001"
      ;((self as any).clients.matchAll as any).mockResolvedValue([])
      vi.mocked(parsePushEventData).mockReturnValueOnce({
        data: { type: "schedule.changed" },
      } as any)
      vi.mocked(buildNotificationDetails).mockReturnValueOnce(
        notificationDetails("Private title", "Private body", {
          type: "schedule.changed",
          recipientUserId,
          notificationId: "private-notification-id",
          url: "/private-message/123",
        })
      )
      const fetchMock = vi.fn()
      vi.stubGlobal("fetch", fetchMock)
      onlineSpy.mockReturnValue(false)
      const event = {
        data: { type: "schedule.changed" },
        waitUntil: vi.fn<(promise: Promise<void>) => void>(),
      }
      const helpers = await vi.importActual<typeof import("@/push/notification-helpers")>(
        "@/push/notification-helpers"
      )

      eventListeners.push?.(event)
      await event.waitUntil.mock.calls[0]?.[0]

      expect(fetchMock).not.toHaveBeenCalled()
      expect((self as any).registration.showNotification).toHaveBeenCalledExactlyOnceWith(
        helpers.getDefaultNotificationTitle(),
        {
          body: helpers.getDefaultNotificationBody(),
          icon: helpers.DEFAULT_ICON,
          badge: helpers.DEFAULT_ICON,
          data: { url: "/" },
        }
      )
    })

    it("shows a fallback system notification for empty push data with a visible window", async () => {
      const helpers = await vi.importActual<typeof import("@/push/notification-helpers")>(
        "@/push/notification-helpers"
      )
      vi.mocked(parsePushEventData).mockImplementationOnce(helpers.parsePushEventData)
      vi.mocked(buildNotificationDetails).mockImplementationOnce(helpers.buildNotificationDetails)
      const client = { visibilityState: "visible", postMessage: vi.fn() }
      ;((self as any).clients.matchAll as any).mockResolvedValue([client])
      const event = {
        data: null,
        waitUntil: vi.fn<(promise: Promise<void>) => void>(),
      }

      eventListeners.push?.(event)
      expect(event.waitUntil).toHaveBeenCalledExactlyOnceWith(expect.any(Promise))
      await event.waitUntil.mock.calls[0]?.[0]

      const { title, options } = helpers.buildNotificationDetails({})
      expect((self as any).registration.showNotification).toHaveBeenCalledExactlyOnceWith(
        title,
        options
      )
      expect(client.postMessage).not.toHaveBeenCalled()
    })

    it.each([
      {
        label: "notification ID without a topic",
        metadata: {
          notificationId: "notification-1",
          recipientUserId: "00000000-0000-4000-8000-000000000001",
        },
        messageFields: {
          notificationId: "notification-1",
          recipientUserId: "00000000-0000-4000-8000-000000000001",
        },
        toastFields: {
          id: "notification-1",
          data: {
            url: "/target",
            type: "in-app",
            notificationId: "notification-1",
            recipientUserId: "00000000-0000-4000-8000-000000000001",
          },
        },
      },
      {
        label: "topic without a notification ID",
        metadata: {
          topic: "news.published",
          recipientUserId: "00000000-0000-4000-8000-000000000001",
        },
        messageFields: {
          topic: "news.published",
          recipientUserId: "00000000-0000-4000-8000-000000000001",
        },
        toastFields: {
          data: {
            url: "/target",
            type: "in-app",
            topic: "news.published",
            recipientUserId: "00000000-0000-4000-8000-000000000001",
          },
        },
      },
      {
        label: "non-string metadata",
        metadata: { notificationId: 42, topic: true, recipientUserId: 42 },
        messageFields: {},
        toastFields: {},
      },
    ])(
      "delivers formatted toast content with $label",
      async ({ metadata, messageFields, toastFields }) => {
        const helpers = await vi.importActual<typeof import("@/push/notification-helpers")>(
          "@/push/notification-helpers"
        )
        vi.mocked(parsePushEventData).mockImplementationOnce(helpers.parsePushEventData)
        vi.mocked(buildNotificationDetails).mockImplementationOnce(helpers.buildNotificationDetails)
        const client = { visibilityState: "visible", postMessage: vi.fn() }
        ;((self as any).clients.matchAll as any).mockResolvedValue([client])
        const event = {
          data: {
            json: () => ({
              title: "  Formatted title  ",
              body: "  Formatted body  ",
              url: "/target",
              data: { type: "in-app", ...metadata },
            }),
            text: () => "",
          },
          waitUntil: vi.fn<(promise: Promise<void>) => void>(),
        }

        eventListeners.push?.(event)
        expect(event.waitUntil).toHaveBeenCalledExactlyOnceWith(expect.any(Promise))
        await event.waitUntil.mock.calls[0]?.[0]

        expect(client.postMessage).toHaveBeenCalledExactlyOnceWith({
          type: "PUSH_NOTIFICATION",
          ...messageFields,
          toast: {
            title: "Formatted title",
            body: "Formatted body",
            url: "/target",
            ...toastFields,
          },
        })
        expect((self as any).registration.showNotification).not.toHaveBeenCalled()
      }
    )
  })

  describe("Notification Click Event Handler", () => {
    it("registers notificationclick event listener", () => {
      expect(self.addEventListener).toHaveBeenCalledWith("notificationclick", expect.any(Function))
      expect(eventListeners.notificationclick).toBeDefined()
    })

    it("opens the root without queuing or reporting when a notification has no data", async () => {
      ;((self as any).clients.matchAll as any).mockResolvedValue([])
      ;((self as any).clients.openWindow as any).mockResolvedValue({})
      const fetchMock = vi.fn()
      vi.stubGlobal("fetch", fetchMock)
      const event = {
        notification: { close: vi.fn(), data: null },
        waitUntil: vi.fn<(promise: Promise<void>) => void>(),
      }

      eventListeners.notificationclick?.(event)
      expect(event.waitUntil).toHaveBeenCalledExactlyOnceWith(expect.any(Promise))
      await event.waitUntil.mock.calls[0]?.[0]

      expect(event.notification.close).toHaveBeenCalledOnce()
      expect((self as any).clients.matchAll).toHaveBeenCalledExactlyOnceWith({
        type: "window",
        includeUncontrolled: true,
      })
      expect((self as any).clients.openWindow).toHaveBeenCalledExactlyOnceWith(
        `${location.origin}/`
      )
      expect(fetchMock).not.toHaveBeenCalled()
      expect(storePendingNavigation).not.toHaveBeenCalled()
      expect(storePendingReport).not.toHaveBeenCalled()
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
      expect(storePendingNavigation).not.toHaveBeenCalled()
      expect(storePendingReport).not.toHaveBeenCalled()
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

    it("uses the normalized metadata URL when the top-level push URL is empty", async () => {
      const helpers = await vi.importActual<typeof import("@/push/notification-helpers")>(
        "@/push/notification-helpers"
      )
      vi.mocked(parsePushEventData).mockImplementationOnce(helpers.parsePushEventData)
      vi.mocked(buildNotificationDetails).mockImplementationOnce(helpers.buildNotificationDetails)

      const mockClient = {
        visibilityState: "visible",
        postMessage: vi.fn(),
      }
      ;((self as any).clients.matchAll as any).mockResolvedValue([mockClient])

      const mockEvent = {
        data: {
          json: () => ({
            title: "Fallback title",
            body: "Fallback body",
            url: "",
            data: { type: "in-app", url: "/fallback-url" },
          }),
          text: () => "",
        },
        waitUntil: vi.fn((promise) => promise),
      }

      await (eventListeners.push as any)(mockEvent)
      expect(mockEvent.waitUntil).toHaveBeenCalledExactlyOnceWith(expect.any(Promise))
      await mockEvent.waitUntil.mock.calls[0]?.[0]

      expect(mockClient.postMessage).toHaveBeenCalledWith({
        type: "PUSH_NOTIFICATION",
        toast: { title: "Fallback title", body: "Fallback body", url: "/fallback-url" },
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

    it.each([undefined, null])(
      "uses root and default body when the in-app payload has no top-level URL and metadata URL is %s",
      async (url) => {
        const helpers = await vi.importActual<typeof import("@/push/notification-helpers")>(
          "@/push/notification-helpers"
        )
        vi.mocked(parsePushEventData).mockImplementationOnce(helpers.parsePushEventData)
        vi.mocked(buildNotificationDetails).mockImplementationOnce(helpers.buildNotificationDetails)
        const mockClient = { visibilityState: "visible", postMessage: vi.fn() }
        ;((self as any).clients.matchAll as any).mockResolvedValue([mockClient])

        const mockEvent = {
          data: {
            json: () => ({ title: "Root fallback", data: { type: "in-app", url } }),
            text: () => "",
          },
          waitUntil: vi.fn((promise) => promise),
        }
        await (eventListeners.push as any)(mockEvent)
        expect(mockEvent.waitUntil).toHaveBeenCalledExactlyOnceWith(expect.any(Promise))
        await mockEvent.waitUntil.mock.calls[0]?.[0]

        expect(mockClient.postMessage).toHaveBeenCalledWith({
          type: "PUSH_NOTIFICATION",
          toast: {
            title: "Root fallback",
            body: helpers.getDefaultNotificationBody(),
            url: "/",
          },
        })
      }
    )

    it("delivers a toast when optional notification metadata is absent", async () => {
      const helpers = await vi.importActual<typeof import("@/push/notification-helpers")>(
        "@/push/notification-helpers"
      )
      vi.mocked(parsePushEventData).mockImplementationOnce(helpers.parsePushEventData)
      vi.mocked(buildNotificationDetails).mockImplementationOnce(helpers.buildNotificationDetails)
      const mockClient = { visibilityState: "visible", postMessage: vi.fn() }
      ;((self as any).clients.matchAll as any).mockResolvedValue([mockClient])
      const mockEvent = {
        data: {
          json: () => ({
            title: "No metadata",
            body: "Fallback body",
            url: "/payload-url",
            data: { type: "in-app" },
          }),
          text: () => "",
        },
        waitUntil: vi.fn((promise) => promise),
      }

      await (eventListeners.push as any)(mockEvent)
      expect(mockEvent.waitUntil).toHaveBeenCalledExactlyOnceWith(expect.any(Promise))
      await mockEvent.waitUntil.mock.calls[0]?.[0]

      expect(mockClient.postMessage).toHaveBeenCalledWith({
        type: "PUSH_NOTIFICATION",
        toast: { title: "No metadata", body: "Fallback body", url: "/payload-url" },
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
      expect(storePendingNavigation).not.toHaveBeenCalled()
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
