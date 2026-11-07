import type { Page } from "@playwright/test"

export function pageErrorsThroughReady(
  page: Page,
  waitForReady: () => Promise<unknown>
): Promise<string[]>
