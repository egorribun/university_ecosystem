import { expect, type Page } from "@playwright/test";

type NewsLogEntry = {
  header: string | undefined;
  status: number;
};

type MockState = {
  loggedIn: boolean;
  newsVersion: string;
  offline: boolean;
  newsLog: NewsLogEntry[];
  notifications: MockNotification[];
  pushSubscription: { endpoint: string; topics: string[] } | null;
};

const mockUser = {
  id: 1,
  full_name: "Иван Иванов",
  role: "student",
  group_id: "iu-21",
};

const mockNews = [
  {
    id: 1,
    title: "Новость дня",
    content: "Кампус переходит на новую систему расписаний.",
    created_at: "2025-01-01T10:00:00Z",
  },
  {
    id: 2,
    title: "Библиотека открыта",
    content: "Расширены часы работы библиотечного центра.",
    created_at: "2025-01-03T12:30:00Z",
  },
];

const mockEvents = [
  {
    id: 10,
    title: "Хакатон ГУУ",
    description: "Командные соревнования по разработке.",
    starts_at: "2025-01-05T09:00:00",
    location: "Актовый зал",
  },
];

const mockSchedule = [
  {
    id: 101,
    subject: "Математика",
    teacher: "Проф. Смирнов",
    room: "А-101",
    lesson_type: "Лекция",
    weekday: "Понедельник",
    start_time: "09:00",
    end_time: "10:30",
    parity: "both" as const,
  },
];

const mockGroups = [
  { id: 1, name: "ИУ-21", course: 1, faculty: "ИТ" },
  { id: 2, name: "БИ-22", course: 2, faculty: "Бизнес" },
];

type MockNotification = {
  id: number;
  title: string;
  body?: string;
  type?: string;
  url?: string;
  created_at: string;
  read: boolean;
  read_at?: string | null;
};

const mockNotificationsSeed: MockNotification[] = [
  {
    id: 101,
    title: "Новое расписание",
    body: "Расписание обновлено",
    type: "schedule",
    url: "/schedule",
    created_at: new Date("2025-01-03T09:30:00Z").toISOString(),
    read: false,
    read_at: null,
  },
  {
    id: 102,
    title: "Новости кампуса",
    body: "Открылся новый корпус",
    type: "news",
    url: "/news",
    created_at: new Date("2025-01-02T11:00:00Z").toISOString(),
    read: true,
    read_at: new Date("2025-01-02T12:00:00Z").toISOString(),
  },
];

export async function useMockApi(page: Page) {
  const state: MockState = {
    loggedIn: false,
    newsVersion: '"news-v1"',
    offline: false,
    newsLog: [],
    notifications: mockNotificationsSeed.map(notification => ({ ...notification })),
    pushSubscription: null,
  };

  await page.addInitScript(() => {
    try {
      if (window.name !== "__mock_api_initialized__") {
        window.localStorage.clear();
        window.sessionStorage.clear();
        window.name = "__mock_api_initialized__";
      }
    } catch {}
  });

  page.on("console", (msg) => {
    const location = msg.location();
    console.log(`[console:${msg.type()}] ${msg.text()}${location?.url ? ` (${location.url})` : ""}`);
  });

  page.on("pageerror", (error) => {
    console.log(`[pageerror] ${error.message}\n${error.stack ?? ""}`);
  });

  page.on("requestfailed", (request) => {
    console.log(`[requestfailed] ${request.url()} :: ${request.failure()?.errorText ?? "unknown"}`);
  });

  page.on("response", (response) => {
    const type = response.request().resourceType();
    const contentType = response.headers()["content-type"] ?? "";
    if (type === "script" && contentType.includes("text/html")) {
      console.log(`[response] unexpected HTML for script: ${response.url()} status=${response.status()}`);
    }
  });

  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const pathname = url.pathname.replace(/^\/+/u, "");
    const method = route.request().method().toUpperCase();

    if (!pathname.startsWith("api/")) {
      await route.continue();
      return;
    }

    if (pathname === "api/auth/login") {
      const postData = route.request().postData() ?? "";
      const params = new URLSearchParams(postData);
      const username = params.get("username");
      const password = params.get("password");

      if (username === "student@example.com" && password === "Password123") {
        state.loggedIn = true;
        console.log("[mock] login success");
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ access_token: "mock-token" }),
        });
        return;
      }

      await route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Unauthorized" }),
      });
      return;
    }

    if (method === "OPTIONS") {
      await route.fulfill({
        status: 200,
        headers: {
          "access-control-allow-origin": url.origin,
          "access-control-allow-credentials": "true",
          "access-control-allow-methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
          "access-control-allow-headers": "*",
        },
      });
      return;
    }

    if (pathname === "api/users/me") {
      const auth = route.request().headers()["authorization"];
      console.log(`[mock] /users/me -> loggedIn=${state.loggedIn} auth=${auth ?? "none"}`);
      if (state.loggedIn || auth?.includes("mock-token")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(mockUser),
        });
      } else {
        await route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Unauthorized" }),
        });
      }
      return;
    }

    if (pathname.startsWith("api/events")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(mockEvents),
      });
      return;
    }

    if (pathname.startsWith("api/schedule/ics")) {
      const body = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "BEGIN:VEVENT",
        "SUMMARY:Математика",
        "DTSTART:20240101T090000",
        "DTEND:20240101T103000",
        "END:VEVENT",
        "END:VCALENDAR",
      ].join("\r\n");

      await route.fulfill({
        status: 200,
        contentType: "text/calendar",
        headers: {
          "content-disposition": "attachment; filename=\"schedule-iu-21.ics\"",
        },
        body,
      });
      return;
    }

    if (pathname.startsWith("api/schedule")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(mockSchedule),
      });
      return;
    }

    if (pathname === "api/groups") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(mockGroups),
      });
      return;
    }

    if (pathname.startsWith("api/news")) {
      const headers = route.request().headers();
      const ifNoneMatch = headers["if-none-match"];

      if (state.offline) {
        state.newsLog.push({ header: ifNoneMatch, status: 503 });
        await route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({ detail: "offline" }),
        });
        return;
      }

      if (ifNoneMatch && ifNoneMatch === state.newsVersion) {
        state.newsLog.push({ header: ifNoneMatch, status: 304 });
        await route.fulfill({
          status: 304,
          headers: { etag: state.newsVersion },
        });
        return;
      }

      state.newsLog.push({ header: ifNoneMatch, status: 200 });
      await route.fulfill({
        status: 200,
        headers: { etag: state.newsVersion, "content-type": "application/json" },
        body: JSON.stringify(mockNews),
      });
      return;
    }

    if (pathname.startsWith("api/stats")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({}),
      });
      return;
    }

    if (pathname === "api/notifications") {
      const items = state.notifications.map(notification => ({
        id: notification.id,
        title: notification.title,
        body: notification.body,
        type: notification.type,
        url: notification.url,
        created_at: notification.created_at,
        read: notification.read,
        read_at: notification.read_at ?? null,
      }))
      const unreadCount = items.reduce((acc, item) => acc + (item.read ? 0 : 1), 0)
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items,
          unread_count: unreadCount,
          has_more: false,
          next_cursor: null,
        }),
      })
      return
    }

    const readMatch = pathname.match(/^api\/notifications\/(\d+)\/read$/)
    if (readMatch) {
      const id = Number(readMatch[1])
      const iso = new Date().toISOString()
      state.notifications = state.notifications.map(notification =>
        notification.id === id
          ? { ...notification, read: true, read_at: notification.read_at ?? iso }
          : notification,
      )
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true }),
      })
      return
    }

    if (pathname === "api/notifications/read-all") {
      const iso = new Date().toISOString()
      state.notifications = state.notifications.map(notification => ({
        ...notification,
        read: true,
        read_at: notification.read_at ?? iso,
      }))
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true }),
      })
      return
    }

    if (pathname === "api/push/subscribe" && method === "POST") {
      const payload = JSON.parse(route.request().postData() || "{}") as {
        endpoint?: string
        keys?: { auth?: string; p256dh?: string }
        topics?: unknown
      }
      const endpoint = (payload.endpoint ?? "").trim()
      const auth = payload.keys?.auth ?? ""
      const p256dh = payload.keys?.p256dh ?? ""
      const topics = Array.isArray(payload.topics)
        ? (payload.topics.filter((value): value is string => typeof value === "string") as string[])
        : []
      state.pushSubscription = { endpoint, topics }
      const now = new Date().toISOString()
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: 1,
          user_id: mockUser.id,
          endpoint,
          p256dh,
          auth,
          created_at: now,
          updated_at: now,
          topics,
        }),
      })
      return
    }

    if (pathname === "api/push/unsubscribe" && method === "POST") {
      state.pushSubscription = null
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true }),
      })
      return
    }

    if (pathname === "api/push/test" && method === "POST") {
      const subscribed = state.pushSubscription != null
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          sent: subscribed ? 1 : 0,
          removed: 0,
          failed: subscribed ? 0 : 1,
          detail: subscribed ? undefined : "Нет активной подписки",
        }),
      })
      return
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({}),
    });
  });

  return {
    state,
    goOffline(value: boolean) {
      state.offline = value;
    },
    async login(currentPage: Page) {
      await currentPage.goto("/login", { waitUntil: "domcontentloaded" });
      await currentPage.waitForURL(/\/login$/);
      await currentPage.waitForSelector('input[name="username"]', { state: "visible" });
      const emailField = currentPage.locator('input[name="username"]');
      await emailField.fill("student@example.com");
      await currentPage.locator('input[name="password"]').fill("Password123");
      await currentPage.getByRole("button", { name: "Войти" }).click();
      await expect(currentPage).toHaveURL(/\/dashboard$/);
    },
  };
}

export type { MockState };
