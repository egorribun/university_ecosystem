import type { Page } from "@playwright/test"

type Scenario = "news" | "events" | "schedule" | "release" | "reply"
export type PushRotationObservation = {
  arm: (scenario: Scenario) => void
  optIn: (timeoutMs: number) => Promise<void>
  beforeWait: (scenario: Scenario, timeoutMs: number) => Promise<void>
  reportFailure: (timeoutMs: number) => Promise<void>
}
export function createPushRotationObservation(
  page: Page,
  project: string,
  retry: number,
  emit?: (line: string) => unknown,
  scope?: "topics" | "reply"
): PushRotationObservation
