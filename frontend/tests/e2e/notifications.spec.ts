import { expect, test, type Page } from "./test"
import { useMockApi } from "./utils/mockApi"

const E2E_TIMEOUTS = {
  toast: 15000,
}

interface MockPushAction {
  action: string
  title: string
  icon?: string
  url?: string
}

interface MockPushPayload {
  title?: string
  body?: string
  url?: string
  icon?: string
  tag?: string
  timestamp?: number
  actions?: { action?: unknown; title?: unknown; icon?: unknown; url?: unknown }[]
  data?: Record<string, unknown>
}

async function setupMockServiceWorker(page: Page) {
  await page.addInitScript(() => {
    const messageListeners = new Set<EventListener>()
    const showNotificationCalls: Array<{ title: string; options: NotificationOptions } | unknown> =
      []

    const registration = {
      showNotification(title: string, options: NotificationOptions = {}) {
        showNotificationCalls.push({ title, options })
        return Promise.resolve()
      },
      addEventListener: () => {},
      removeEventListener: () => {},
      unregister: () => Promise.resolve(true),
      active: null,
      waiting: null,
      installing: null,
    } as unknown as ServiceWorkerRegistration

    const wrapListener = (listener: EventListenerOrEventListenerObject | null | undefined) => {
      if (!listener) return undefined
      if (typeof listener === "function") return listener as EventListener
      if (
        typeof listener === "object" &&
        typeof (listener as EventListenerObject).handleEvent === "function"
      ) {
        return (event: Event) => (listener as EventListenerObject).handleEvent(event)
      }
      return undefined
    }

    const serviceWorkerContainer: ServiceWorkerContainer = {
      controller: {} as ServiceWorker,
      ready: Promise.resolve(registration),
      register: async () => registration,
      getRegistrations: async () => [registration],
      getRegistration: async () => registration,
      addEventListener(type: string, listener: EventListenerOrEventListenerObject | null) {
        if (type !== "message") return
        const wrapped = wrapListener(listener)
        if (wrapped) messageListeners.add(wrapped)
      },
      removeEventListener(type: string, listener: EventListenerOrEventListenerObject | null) {
        if (type !== "message") return
        const wrapped = wrapListener(listener)
        if (wrapped) messageListeners.delete(wrapped)
      },
      dispatchEvent: () => false,
      oncontrollerchange: null,
      onmessage: null,
      onmessageerror: null,
      startMessages: () => {},
    } as unknown as ServiceWorkerContainer

    // Let the shared API fixture distinguish this intentional test double
    // from a browser-native service-worker container on Firefox/WebKit.
    Object.defineProperty(serviceWorkerContainer, "__e2eMockServiceWorker", {
      configurable: false,
      enumerable: false,
      value: true,
    })

    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: serviceWorkerContainer,
    })

    const dispatchMessage = (data: unknown) => {
      const event = new MessageEvent("message", {
        data,
        origin: window.location.origin,
        source: window,
      })
      messageListeners.forEach((listener) => {
        try {
          listener.call(serviceWorkerContainer, event)
        } catch (error) {
          console.error("Mock service worker listener failed", error)
        }
      })
      if (typeof serviceWorkerContainer.onmessage === "function") {
        try {
          serviceWorkerContainer.onmessage.call(serviceWorkerContainer, event)
        } catch (error) {
          console.error("Mock service worker onmessage failed", error)
        }
      }
    }

    const normalizeActions = (raw: unknown): MockPushAction[] => {
      if (!Array.isArray(raw)) return []
      const result: MockPushAction[] = []
      for (const entry of raw) {
        if (!entry || typeof entry !== "object") continue
        const actionValue = (entry as { action?: unknown }).action
        const titleValue = (entry as { title?: unknown }).title
        const key = typeof actionValue === "string" ? actionValue.trim() : ""
        const title = typeof titleValue === "string" ? titleValue.trim() : ""
        if (!key || !title) continue
        const item: MockPushAction = { action: key, title }
        const iconValue = (entry as { icon?: unknown }).icon
        if (typeof iconValue === "string") {
          item.icon = iconValue
        }
        const urlValue = (entry as { url?: unknown }).url
        if (typeof urlValue === "string") {
          const trimmed = urlValue.trim()
          if (trimmed) item.url = trimmed
        }
        result.push(item)
      }
      return result
    }

    const defaultIcon = "/maskable-icon-192.png"

    const state: {
      lastToast: null | {
        toast: {
          title?: string
          body?: string
          url: string
          icon?: string
          tag?: string
          data: Record<string, unknown>
          timestamp?: number
        }
        actions: MockPushAction[]
      }
    } = {
      lastToast: null,
    }

    ;(
      window as unknown as { __getShowNotificationCalls: () => unknown[] }
    ).__getShowNotificationCalls = () => [...showNotificationCalls]
    ;(
      window as unknown as { __getMockServiceWorkerMessageListenerCount: () => number }
    ).__getMockServiceWorkerMessageListenerCount = () => messageListeners.size

    window.__mockPush = async (payload: unknown) => {
      // Cast payload safely
      const p = payload as MockPushPayload | null

      const actions = normalizeActions(p?.actions)
      const data: Record<string, unknown> =
        p && p.data && typeof p.data === "object" ? { ...(p.data as Record<string, unknown>) } : {}

      const rawUrl = typeof p?.url === "string" ? p.url : (data.url as string | undefined)
      const resolvedUrl = rawUrl && rawUrl.trim() ? rawUrl.trim() : "/"
      data.url = resolvedUrl

      if (actions.length) {
        const actionUrls: Record<string, string> = {}
        for (const action of actions) {
          if (action.url) actionUrls[action.action] = action.url
        }
        if (Object.keys(actionUrls).length) {
          data.actionUrls = actionUrls
        }
      }

      const toast = {
        title: typeof p?.title === "string" && p.title.trim() ? p.title : "Экосистема ГУУ",
        body: typeof p?.body === "string" ? p.body : undefined,
        url: resolvedUrl,
        icon: typeof p?.icon === "string" && p.icon.trim() ? p.icon : defaultIcon,
        tag: typeof p?.tag === "string" ? p.tag : undefined,
        data,
        timestamp: typeof p?.timestamp === "number" ? p.timestamp : Date.now(),
      }

      state.lastToast = { toast, actions }

      if (data.type === "in-app") {
        try {
          dispatchMessage({ type: "PUSH_NOTIFICATION", toast })
        } catch (e) {
          console.error("Dispatch failed", e)
        }
        return
      }

      type NotificationOptionsWithActions = NotificationOptions & {
        actions?: Array<{ action: string; title: string; icon?: string }>
      }

      const options: NotificationOptionsWithActions = {
        body: toast.body,
        icon: toast.icon,
        badge: toast.icon,
        tag: toast.tag,
        data,
      }

      if (actions.length) {
        options.actions = actions.map((a) => ({
          action: a.action,
          title: a.title,
          icon: a.icon,
        }))
      }

      void registration.showNotification(toast.title ?? "Экосистема ГУУ", options)
    }
    ;(
      window as unknown as { __mockNotificationClick: (action?: string) => void }
    ).__mockNotificationClick = (action?: string) => {
      const current = state.lastToast
      if (!current) return
      const payload = current.toast
      const data = payload.data || {}
      let target = payload.url
      if (data.actionUrls && typeof data.actionUrls === "object" && action) {
        const urls = data.actionUrls as Record<string, unknown>
        const candidate = urls[action]
        if (typeof candidate === "string" && candidate.trim()) {
          target = candidate
        }
      }
      try {
        const url = new URL(target, window.location.origin)
        window.location.assign(url.href)
      } catch {
        window.location.assign(target)
      }
    }
  })
}

declare global {
  interface Window {
    __mockPush?: (payload: unknown) => void
    __mockNotificationClick?: (action?: string) => void
    __getShowNotificationCalls?: () => unknown[]
    __getMockServiceWorkerMessageListenerCount?: () => number
  }
}

test.describe("Push notifications", () => {
  test.beforeEach(async ({ page }) => {
    await setupMockServiceWorker(page)
  })

  test("navigates to routes defined in notification actions", async ({ page }) => {
    const mock = await useMockApi(page, { serviceWorker: "preserve" })
    await mock.login(page)

    const payload = {
      title: "Обновления портала",
      body: "Появились новые новости и расписание.",
      data: {
        type: "system",
        url: "/dashboard",
        actionUrls: {
          "open-news": "/news",
          "open-schedule": "/schedule",
        },
      },
      actions: [
        { action: "open-news", title: "К новостям", url: "/news" },
        { action: "open-schedule", title: "К расписанию", url: "/schedule" },
      ],
    }

    await page.evaluate(
      ({ payload }) => {
        window.__mockPush?.(payload)
      },
      { payload }
    )

    const notificationCalls = await page.evaluate(
      () => window.__getShowNotificationCalls?.().length ?? 0
    )
    expect(notificationCalls).toBeGreaterThan(0)

    await Promise.all([
      page.waitForURL(/\/news$/),
      page.evaluate(() => {
        window.__mockNotificationClick?.("open-news")
      }),
    ])
    await expect(
      page.getByRole("heading", { name: /Новости университета|University news|News/i }).first()
    ).toBeVisible({ timeout: E2E_TIMEOUTS.toast })

    // A full navigation creates a new document and therefore a fresh SW test
    // double. Seed the same notification before exercising its second action.
    await page.evaluate(({ payload }) => window.__mockPush?.(payload), { payload })
    await Promise.all([
      page.waitForURL(/\/schedule$/),
      page.evaluate(() => {
        window.__mockNotificationClick?.("open-schedule")
      }),
    ])
    await expect(page.getByText(/Моё расписание|My schedule/i)).toBeVisible()
  })

  test("shows in-app toast instead of system notification for visible clients", async ({
    page,
  }) => {
    const mock = await useMockApi(page, { serviceWorker: "preserve" })
    await mock.login(page)

    const initialCalls = await page.evaluate(
      () => window.__getShowNotificationCalls?.().length ?? 0
    )
    expect(initialCalls).toBe(0)

    await page.waitForFunction(
      () => (window.__getMockServiceWorkerMessageListenerCount?.() ?? 0) > 0
    )
    await page.evaluate(
      ({ payload }) => {
        window.__mockPush?.(payload)
      },
      {
        payload: {
          title: "University News Test", // Use ASCII to avoid encoding issues
          body: "Semester start dates have been updated",
          url: "/news",
          data: {
            type: "in-app",
            severity: "success",
          },
        },
      }
    )

    await expect(page.getByRole("heading", { name: "University News Test" })).toBeVisible()
    await expect(page.getByText("Semester start dates have been updated")).toBeVisible()

    const postCalls = await page.evaluate(() => window.__getShowNotificationCalls?.().length ?? 0)
    expect(postCalls).toBe(0)

    await page.getByRole("button", { name: /^(Open|Открыть)$/i }).click()

    await page.waitForURL(/\/news$/)
    // Assert the canonical News route heading. A loading/offline fallback can
    // legitimately render its own h1 during a navigation race, so querying
    // every level-one heading is ambiguous even inside the main landmark.
    const heading = page
      .locator("#main-content")
      .getByRole("heading", { name: /Новости университета|University news/i })
    // Use unicode for robustness against mojibake
    await expect(heading).toContainText(/News|\u041d\u043e\u0432\u043e\u0441\u0442/i)
  })
})
