import type { Page } from "@playwright/test"

export function collectNewsStartupErrors(
  page: Page,
  waitForReady: () => Promise<unknown>
): Promise<{ consoleErrors: string[]; pageErrors: string[] }>
