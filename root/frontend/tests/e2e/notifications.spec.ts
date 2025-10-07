import { expect, test, type Page } from "@playwright/test";
import { useMockApi } from "./utils/mockApi";

async function setupMockServiceWorker(page: Page) {
  await page.addInitScript(() => {
    const messageListeners = new Set<EventListener>();
    const showNotificationCalls: Array<{ title: string; options: NotificationOptions } | unknown> = [];

    window.__mockVapidPublicKey = "AAAA";

    class MockNotification {
      static permission: NotificationPermission = "granted";
      static async requestPermission() {
        return "granted" as NotificationPermission;
      }

      title: string;
      options: NotificationOptions;

      constructor(title: string, options: NotificationOptions = {}) {
        this.title = title;
        this.options = options;
      }

      close() {}
    }

    Object.defineProperty(window, "Notification", { configurable: true, value: MockNotification });

    let pushSubscription: PushSubscription | null = null;

    const createPushSubscription = (options: PushSubscriptionOptionsInit): PushSubscription => {
      const endpoint = `https://push.example.com/${Math.random().toString(36).slice(2)}`;
      const keys = {
        auth: btoa(`auth-${Math.random().toString(36).slice(2)}`),
        p256dh: btoa(`p256-${Math.random().toString(36).slice(2)}`),
      };
      const subscription: PushSubscription = {
        endpoint,
        expirationTime: Date.now() + 7 * 24 * 60 * 60 * 1000,
        options,
        getKey: () => null,
        async unsubscribe() {
          pushSubscription = null;
          return true;
        },
        toJSON() {
          return { endpoint, keys };
        },
      } as PushSubscription;
      return subscription;
    };

    const registration = {
      showNotification(title: string, options: NotificationOptions = {}) {
        showNotificationCalls.push({ title, options });
        return Promise.resolve();
      },
      pushManager: {
        async getSubscription() {
          return pushSubscription;
        },
        async subscribe(options: PushSubscriptionOptionsInit) {
          pushSubscription = createPushSubscription(options);
          return pushSubscription;
        },
      },
    } as ServiceWorkerRegistration;

    const wrapListener = (listener: EventListenerOrEventListenerObject | null | undefined) => {
      if (!listener) return undefined;
      if (typeof listener === "function") return listener as EventListener;
      if (typeof listener === "object" && typeof (listener as EventListenerObject).handleEvent === "function") {
        return (event: Event) => (listener as EventListenerObject).handleEvent(event);
      }
      return undefined;
    };

    const serviceWorkerContainer: ServiceWorkerContainer = {
      controller: {} as ServiceWorker,
      ready: Promise.resolve(registration),
      register: async () => registration,
      getRegistrations: async () => [registration],
      getRegistration: async () => registration,
      addEventListener(type: string, listener: EventListenerOrEventListenerObject | null) {
        if (type !== "message") return;
        const wrapped = wrapListener(listener);
        if (wrapped) messageListeners.add(wrapped);
      },
      removeEventListener(type: string, listener: EventListenerOrEventListenerObject | null) {
        if (type !== "message") return;
        const wrapped = wrapListener(listener);
        if (wrapped) messageListeners.delete(wrapped);
      },
      dispatchEvent: () => false,
      oncontrollerchange: null,
      onmessage: null,
      onmessageerror: null,
      startMessages: () => {},
    } as unknown as ServiceWorkerContainer;

    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: serviceWorkerContainer,
    });

    Object.defineProperty(navigator, "permissions", {
      configurable: true,
      value: {
        async query() {
          return { state: "granted" };
        },
      },
    });

    const dispatchMessage = (data: unknown) => {
      const event = new MessageEvent("message", {
        data,
        origin: window.location.origin,
        source: window,
      });
      messageListeners.forEach((listener) => {
        try {
          listener.call(serviceWorkerContainer, event);
        } catch (error) {
          console.error("Mock service worker listener failed", error);
        }
      });
      if (typeof serviceWorkerContainer.onmessage === "function") {
        try {
          serviceWorkerContainer.onmessage.call(serviceWorkerContainer, event);
        } catch (error) {
          console.error("Mock service worker onmessage failed", error);
        }
      }
    };

    type MockAction = {
      action: string;
      title: string;
      icon?: string;
      url?: string;
    };

    const normalizeActions = (raw: unknown): MockAction[] => {
      if (!Array.isArray(raw)) return [];
      const result: MockAction[] = [];
      for (const entry of raw) {
        if (!entry || typeof entry !== "object") continue;
        const actionValue = (entry as { action?: unknown }).action;
        const titleValue = (entry as { title?: unknown }).title;
        const key = typeof actionValue === "string" ? actionValue.trim() : "";
        const title = typeof titleValue === "string" ? titleValue.trim() : "";
        if (!key || !title) continue;
        const item: MockAction = { action: key, title };
        const iconValue = (entry as { icon?: unknown }).icon;
        if (typeof iconValue === "string") {
          item.icon = iconValue;
        }
        const urlValue = (entry as { url?: unknown }).url;
        if (typeof urlValue === "string") {
          const trimmed = urlValue.trim();
          if (trimmed) item.url = trimmed;
        }
        result.push(item);
      }
      return result;
    };

    const defaultIcon = "/maskable-icon-192.png";

    const state: {
      lastToast: null | {
        toast: {
          title?: string;
          body?: string;
          url: string;
          icon?: string;
          tag?: string;
          data: Record<string, unknown>;
          timestamp?: number;
        };
        actions: MockAction[];
      };
    } = {
      lastToast: null,
    };

    (window as unknown as { __getShowNotificationCalls: () => unknown[] }).__getShowNotificationCalls = () => [...showNotificationCalls];

    (window as unknown as { __mockPush: (payload: any) => void }).__mockPush = (payload: any) => {
      const actions = normalizeActions(payload?.actions);
      const data: Record<string, unknown> =
        payload && payload.data && typeof payload.data === "object"
          ? { ...(payload.data as Record<string, unknown>) }
          : {};

      const rawUrl = typeof payload?.url === "string" ? payload.url : (data.url as string | undefined);
      const resolvedUrl = rawUrl && rawUrl.trim() ? rawUrl.trim() : "/";
      data.url = resolvedUrl;

      if (actions.length) {
        const actionUrls: Record<string, string> = {};
        for (const action of actions) {
          if (action.url) actionUrls[action.action] = action.url;
        }
        if (Object.keys(actionUrls).length) {
          data.actionUrls = actionUrls;
        }
      }

      const toast = {
        title: typeof payload?.title === "string" && payload.title.trim() ? payload.title : "Экосистема ГУУ",
        body: typeof payload?.body === "string" ? payload.body : undefined,
        url: resolvedUrl,
        icon: typeof payload?.icon === "string" && payload.icon.trim() ? payload.icon : defaultIcon,
        tag: typeof payload?.tag === "string" ? payload.tag : undefined,
        data,
        timestamp: typeof payload?.timestamp === "number" ? payload.timestamp : Date.now(),
      };

      state.lastToast = { toast, actions };

      if (data.type === "in-app" && document.visibilityState === "visible") {
        dispatchMessage({ type: "PUSH_NOTIFICATION", toast });
        return;
      }

      type NotificationOptionsWithActions = NotificationOptions & {
        actions?: Array<{ action: string; title: string; icon?: string }>;
      };

      const options: NotificationOptionsWithActions = {
        body: toast.body,
        icon: toast.icon,
        badge: toast.icon,
        tag: toast.tag,
        data,
      };

      if (actions.length) {
        options.actions = actions.map(({ action, title, icon }) => ({ action, title, icon }));
      }

      void registration.showNotification(toast.title ?? "Экосистема ГУУ", options);
    };

    (window as unknown as { __mockNotificationClick: (action?: string) => void }).__mockNotificationClick = (action?: string) => {
      const current = state.lastToast;
      if (!current) return;
      const payload = current.toast;
      const data = payload.data || {};
      let target = payload.url;
      if (data.actionUrls && typeof data.actionUrls === "object" && action) {
        const urls = data.actionUrls as Record<string, unknown>;
        const candidate = urls[action];
        if (typeof candidate === "string" && candidate.trim()) {
          target = candidate;
        }
      }
      try {
        const url = new URL(target, window.location.origin);
        window.location.assign(url.href);
      } catch {
        window.location.assign(target);
      }
    };
  });
}

declare global {
  interface Window {
    __mockPush?: (payload: unknown) => void;
    __mockNotificationClick?: (action?: string) => void;
    __getShowNotificationCalls?: () => unknown[];
    __mockVapidPublicKey?: string;
  }
}

test.describe("Push notifications", () => {
  test.beforeEach(async ({ page }) => {
    await setupMockServiceWorker(page);
  });

  test("navigates to routes defined in notification actions", async ({ page }) => {
    const mock = await useMockApi(page);
    await mock.login(page);

    await page.evaluate(({ payload }) => {
      window.__mockPush?.(payload);
    }, {
      payload: {
        title: "Обновления портала",
        body: "Появились новые новости и расписание.",
        data: { type: "system", url: "/dashboard" },
        actions: [
          { action: "open-news", title: "К новостям", url: "/news" },
          { action: "open-schedule", title: "К расписанию", url: "/schedule" },
        ],
      },
    });

    const notificationCalls = await page.evaluate(() => window.__getShowNotificationCalls?.().length ?? 0);
    expect(notificationCalls).toBeGreaterThan(0);

    await Promise.all([
      page.waitForURL(/\/news$/),
      page.evaluate(() => {
        window.__mockNotificationClick?.("open-news");
      }),
    ]);
    await expect(page.getByText("Новости Университета")).toBeVisible();

    await Promise.all([
      page.waitForURL(/\/schedule$/),
      page.evaluate(() => {
        window.__mockNotificationClick?.("open-schedule");
      }),
    ]);
    await expect(page.getByText("Расписание моей группы")).toBeVisible();
  });

  test("shows in-app toast instead of system notification for visible clients", async ({ page }) => {
    const mock = await useMockApi(page);
    await mock.login(page);

    const initialCalls = await page.evaluate(() => window.__getShowNotificationCalls?.().length ?? 0);
    expect(initialCalls).toBe(0);

    await page.evaluate(({ payload }) => {
      window.__mockPush?.(payload);
    }, {
      payload: {
        title: "Событие началось",
        body: "Хакатон ГУУ стартовал",
        url: "/news",
        data: { type: "in-app", severity: "success" },
      },
    });

    const toast = page.getByRole("alert");
    await expect(toast).toBeVisible();
    await expect(toast).toContainText("Событие началось");
    await expect(toast).toContainText("Хакатон ГУУ стартовал");

    const postCalls = await page.evaluate(() => window.__getShowNotificationCalls?.().length ?? 0);
    expect(postCalls).toBe(0);

    await Promise.all([
      page.waitForURL(/\/news$/),
      page.getByRole("button", { name: "Открыть" }).click(),
    ]);
    await expect(page.getByText("Новости Университета")).toBeVisible();
  });

  test("manages notifications popover and push lifecycle", async ({ page }) => {
    const mock = await useMockApi(page);
    await mock.login(page);

    const bellButton = page.getByRole("button", { name: /Открыть уведомления, непрочитанных: 1/ });
    await expect(bellButton).toBeVisible();
    await bellButton.click();

    const dialog = page.getByRole("dialog", { name: "Уведомления" });
    await expect(dialog).toBeVisible();

    const markSelected = dialog.getByRole("button", { name: "Пометить прочитанным" });
    await expect(markSelected).toBeEnabled();
    await markSelected.click();

    const singleSuccess = page.getByRole("alert").filter({ hasText: "Уведомление помечено прочитанным" });
    await expect(singleSuccess).toBeVisible();

    await expect(dialog.getByText("Все уведомления прочитаны.")).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Пометить все прочитанными" })).toBeDisabled();
    await expect(page.getByRole("button", { name: /непрочитанных нет/ })).toBeVisible();

    const enableSwitch = dialog.getByRole("switch", { name: /Уведомления выключены/ });
    await expect(enableSwitch).toBeEnabled();
    await enableSwitch.click();

    const enabledToast = page.getByRole("alert").filter({ hasText: "Уведомления включены" });
    await expect(enabledToast).toBeVisible();

    const activeSwitch = dialog.getByRole("switch", { name: /Уведомления включены/ });
    await expect(activeSwitch).toBeChecked();
    await expect(activeSwitch).toBeEnabled();

    await page.evaluate(() => {
      window.__mockPush?.({
        title: "Тестовое уведомление",
        body: "Проверка доставки",
        data: { type: "in-app", severity: "info" },
      });
    });

    const testToast = page.getByRole("alert").filter({ hasText: "Тестовое уведомление" });
    await expect(testToast).toBeVisible();

    await activeSwitch.click();
    const disabledToast = page.getByRole("alert").filter({ hasText: "Уведомления выключены" });
    await expect(disabledToast).toBeVisible();
  });
});
