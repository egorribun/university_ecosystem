import { expect, test, type Page } from "@playwright/test";
import { useMockApi } from "./utils/mockApi";

async function setupMockServiceWorker(page: Page) {
  await page.addInitScript(() => {
    const messageListeners = new Set<EventListener>();
    const showNotificationCalls: Array<{ title: string; options: NotificationOptions } | unknown> = [];

    let activeSubscription: PushSubscription | null = null;
    const subscriptionPayload = {
      endpoint: "https://push.example/subscription",
      keys: { p256dh: "p256", auth: "auth" },
    } satisfies PushSubscriptionJSON;

    const createSubscription = () => {
      const applicationServerKey = Uint8Array.from([1, 2, 3, 4]).buffer;
      const authKey = new TextEncoder().encode(subscriptionPayload.keys?.auth ?? "").buffer;

      const sub = {
        endpoint: subscriptionPayload.endpoint!,
        expirationTime: Date.now() + 24 * 3600 * 1000,
        options: {
          applicationServerKey,
          userVisibleOnly: true,
        },
        toJSON: () => subscriptionPayload,
        getKey: (name: PushEncryptionKeyName) => {
          if (name === "p256dh") return applicationServerKey;
          if (name === "auth") return authKey;
          return null;
        },
        unsubscribe: async () => {
          activeSubscription = null;
          return true;
        },
      } satisfies PushSubscription;
      return sub;
    };

    const pushManager: PushManager = {
      getSubscription: async () => activeSubscription,
      subscribe: async () => {
        activeSubscription = createSubscription();
        return activeSubscription;
      },
      permissionState: async () =>
        MockNotification.permission === "default" ? "prompt" : MockNotification.permission,
    };

    const registration = {
      showNotification(title: string, options: NotificationOptions = {}) {
        showNotificationCalls.push({ title, options });
        return Promise.resolve();
      },
      pushManager,
    } as ServiceWorkerRegistration;

    const permissionListeners = new Set<EventListener>();

    let currentPermissionState: PermissionState = "prompt";

    const permissionStatus = {
      get state() {
        return currentPermissionState;
      },
      onchange: null as ((this: PermissionStatus, event: Event) => void) | null,
      addEventListener(type: string, listener: EventListenerOrEventListenerObject | null) {
        if (type !== "change") return;
        const wrapped = wrapListener(listener);
        if (wrapped) permissionListeners.add(wrapped);
      },
      removeEventListener(type: string, listener: EventListenerOrEventListenerObject | null) {
        if (type !== "change") return;
        const wrapped = wrapListener(listener);
        if (wrapped) permissionListeners.delete(wrapped);
      },
      dispatchEvent(event: Event) {
        if (event.type !== "change") return true;
        permissionListeners.forEach((listener) => {
          try {
            listener.call(permissionStatus, event);
          } catch (error) {
            console.error("Mock permission listener failed", error);
          }
        });
        return true;
      },
    } as PermissionStatus & { onchange: ((this: PermissionStatus, event: Event) => void) | null };

    const updatePermission = (next: NotificationPermission) => {
      MockNotification.permission = next;
      currentPermissionState = next === "default" ? "prompt" : next;
      const changeEvent = new Event("change");
      permissionListeners.forEach((listener) => {
        try {
          listener.call(permissionStatus, changeEvent);
        } catch (error) {
          console.error("Mock permission listener failed", error);
        }
      });
      try {
        permissionStatus.onchange?.call(permissionStatus, changeEvent);
      } catch (error) {
        console.error("Mock permission onchange failed", error);
      }
    };

    class MockNotification {
      static permission: NotificationPermission = "default";

      static async requestPermission(): Promise<NotificationPermission> {
        updatePermission("granted");
        return MockNotification.permission;
      }

      constructor(public title: string, public options?: NotificationOptions) {
        this.title = title;
        this.options = options;
      }
    }

    Object.defineProperty(window, "Notification", {
      configurable: true,
      value: MockNotification,
    });

    Object.defineProperty(navigator, "permissions", {
      configurable: true,
      value: {
        query: async () => permissionStatus,
      },
    });

    Object.defineProperty(window, "PushManager", {
      configurable: true,
      value: function MockPushManager() {},
    });

    updatePermission("default");

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

  test("opens popover and marks notifications as read", async ({ page }) => {
    const mock = await useMockApi(page);
    await mock.login(page);

    const bell = page.getByRole("button", { name: /Открыть уведомления/ });
    await expect(bell).toHaveAttribute("aria-label", /непрочитанных: 1/);

    await bell.click();
    const dialog = page.getByRole("dialog", { name: "Уведомления" });
    await expect(dialog).toBeVisible();

    const firstItem = dialog.getByRole("listitem").first();
    await expect(firstItem).toContainText("Изменение расписания");

    await page.getByRole("button", { name: "Пометить прочитанным" }).click();
    await expect(page.getByRole("alert")).toContainText("Уведомление помечено прочитанным");
    await expect(dialog.getByText("Все уведомления прочитаны.")).toBeVisible();

    await expect.poll(() => mock.state.notifications.filter((item) => !item.read).length).toBe(0);
    await expect(bell).toHaveAttribute("aria-label", /непрочитанных нет/);
  });

  test("subscribes, receives test push and unsubscribes from popover", async ({ page }) => {
    const mock = await useMockApi(page);
    await mock.login(page);

    const bell = page.getByRole("button", { name: /Открыть уведомления/ });
    await bell.click();

    const dialog = page.getByRole("dialog", { name: "Уведомления" });
    await expect(dialog).toBeVisible();

    const toggle = dialog.getByRole("switch");
    await expect(toggle).toHaveAttribute("aria-checked", "false");
    await toggle.click();

    await expect(dialog.getByText(/Подписка активна/)).toBeVisible();
    await expect.poll(() => mock.state.pushSubscribed).toBeTruthy();

    await page.evaluate(() => {
      window.__mockPush?.({
        title: "Тестовое уведомление",
        body: "Проверка доставки",
        data: { type: "in-app", url: "/notifications" },
      });
    });

    const toast = page.getByRole("alert");
    await expect(toast).toContainText("Тестовое уведомление");

    await toggle.click();
    await expect(dialog.getByText(/Уведомления выключены/)).toBeVisible();
    await expect(toggle).toHaveAttribute("aria-checked", "false");
    await expect.poll(() => mock.state.pushSubscribed).toBeFalsy();
  });
});
