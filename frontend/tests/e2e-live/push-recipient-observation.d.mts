import type { Page } from "@playwright/test"

type Scenario = "chat" | "reply" | "news" | "events" | "schedule" | "release"

export function createPushRecipientObservation(
  page: Page,
  origin: string,
  project: string,
  retry: number,
  emit?: (line: string) => unknown
): {
  arm: (scenario: Scenario, owner: unknown) => void
  report: (expectedEndpoint: unknown, timeoutMs: number) => Promise<void>
  dispose: () => void
}
