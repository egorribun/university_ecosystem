import { expect, test } from "@playwright/test";
import { useMockApi } from "./utils/mockApi";

test.describe("PWA offline support", () => {
  test("shows offline fallback page when network is unavailable", async ({ page, context }) => {
    const mock = await useMockApi(page);
    await mock.login(page);

    await page.waitForLoadState("networkidle");
    await page.evaluate(async () => {
      await navigator.serviceWorker?.ready;
    });

    const hasController = await page.evaluate(() => Boolean(navigator.serviceWorker?.controller));
    if (!hasController) {
      await page.reload({ waitUntil: "networkidle" });
      await page.evaluate(async () => {
        await navigator.serviceWorker?.ready;
      });
    }

    await page.goto("/offline.html", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "Нет подключения к сети" })).toBeVisible();

    await page.goto("/dashboard", { waitUntil: "networkidle" });

    await context.setOffline(true);
    try {
      await page.goto("/news", { waitUntil: "domcontentloaded" });
      await expect(page.getByRole("heading", { name: "Нет подключения к сети" })).toBeVisible();
      await expect(
        page.getByText("Расписание и новости, просмотренные ранее, останутся доступными офлайн.")
      ).toBeVisible();
    } finally {
      await context.setOffline(false);
    }
  });

  test("profile data stays available offline after it was cached", async ({ page, context }) => {
    const mock = await useMockApi(page);
    await mock.login(page);

    await page.waitForLoadState("networkidle");
    await page.evaluate(async () => {
      await navigator.serviceWorker?.ready;
    });

    let controlled = await page.evaluate(() => Boolean(navigator.serviceWorker?.controller));
    if (!controlled) {
      await page.reload({ waitUntil: "networkidle" });
      await page.evaluate(async () => {
        await navigator.serviceWorker?.ready;
      });
      controlled = await page.evaluate(() => Boolean(navigator.serviceWorker?.controller));
    }

    await page.goto("/profile", { waitUntil: "networkidle" });
    await expect(page).toHaveURL(/\/profile/);
    await expect(page.getByText("Иван Иванов")).toBeVisible();

    await context.setOffline(true);
    try {
      await page.reload({ waitUntil: "domcontentloaded" });
      await expect(page).toHaveURL(/\/profile/);
      await expect(page.getByText("Иван Иванов")).toBeVisible();
    } finally {
      await context.setOffline(false);
    }
  });
});
