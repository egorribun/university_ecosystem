import { expect, test } from "@playwright/test";

type NewsLogEntry = {
  header: string | undefined;
  status: number;
};

type MockState = {
  loggedIn: boolean;
  newsVersion: string;
  offline: boolean;
  newsLog: NewsLogEntry[];
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

async function useMockApi(page: import("@playwright/test").Page) {
  const state: MockState = {
    loggedIn: false,
    newsVersion: '"news-v1"',
    offline: false,
    newsLog: [],
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

    if (pathname.startsWith("api/schedule")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(mockSchedule),
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
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [], unread_count: 0, has_more: false }),
      });
      return;
    }

    if (pathname === "api/notifications/mark-read" || pathname === "api/notifications/mark-all-read") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true }),
      });
      return;
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
    async login(page: import("@playwright/test").Page) {
      await page.goto("/login", { waitUntil: "domcontentloaded" });
      await page.waitForURL(/\/login$/);
      await page.waitForSelector('input[name="username"]', { state: "visible" });
      const emailField = page.locator('input[name="username"]');
      await emailField.fill("student@example.com");
      await page.locator('input[name="password"]').fill("Password123");
      await page.getByRole("button", { name: "Войти" }).click();
      await expect(page).toHaveURL(/\/dashboard$/);
    },
  };
}

test.describe("University ecosystem app", () => {
  test("allows a student to login and reach the dashboard", async ({ page }) => {
    const { login } = await useMockApi(page);
    await login(page);

    await expect(page.getByText(/Иван!/)).toBeVisible();
    const newsLink = page.getByRole("link", { name: "Новости" }).first();
    await expect(newsLink).toBeVisible();
  });

  test("supports navigation between main sections", async ({ page }) => {
    const { login } = await useMockApi(page);
    await login(page);

    await page.getByRole("link", { name: "Смотреть все новости" }).click();
    await expect(page).toHaveURL(/\/news$/);
    await expect(page.getByText("Новости Университета")).toBeVisible();

    await page.getByRole("link", { name: "На главную" }).first().click();
    await expect(page).toHaveURL(/\/dashboard$/);

    await page.getByRole("link", { name: "Перейти к полному расписанию" }).click();
    await expect(page).toHaveURL(/\/schedule$/);
    await expect(page.getByText("Расписание моей группы")).toBeVisible();
  });

  test("caches news responses using ETag", async ({ page }) => {
    const mock = await useMockApi(page);
    await mock.login(page);

    await page.getByRole("link", { name: "Смотреть все новости" }).click();
    await expect(page.getByText("Новость дня")).toBeVisible();

    const cached = await page.evaluate(() => localStorage.getItem("news:list"));
    expect(cached).not.toBeNull();

    await page.reload();
    await expect(page.getByText("Новость дня")).toBeVisible();

    expect(mock.state.newsLog.some((entry) => entry.status === 304)).toBeTruthy();
    expect(mock.state.newsLog.filter((entry) => entry.status === 200).length).toBeGreaterThan(0);
  });

  test("reuses cached news data when the API is offline", async ({ page }) => {
    const mock = await useMockApi(page);
    await mock.login(page);

    await page.getByRole("link", { name: "Смотреть все новости" }).click();
    await expect(page.getByText("Новость дня")).toBeVisible();

    mock.goOffline(true);
    await page.reload();

    await expect(page.getByText("Новость дня")).toBeVisible();
    expect(mock.state.newsLog.some((entry) => entry.status === 503)).toBeTruthy();
  });
});
