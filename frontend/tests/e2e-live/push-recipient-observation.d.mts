import type { Page } from "@playwright/test"

type Scenario = "chat" | "reply" | "news" | "events" | "schedule" | "release"

export function reportPushCleanupObservation(
  context: {
    project: string
    retry: number
    case: "topics" | "chat" | "reply"
    bound: boolean
  } | null,
  removed: unknown,
  emit?: (line: string) => unknown
): void

export function observePushCleanup(
  context: {
    project: string
    retry: number
    case: "topics" | "chat" | "reply"
    bound: boolean
  } | null,
  cleanup: () => Promise<boolean | null>,
  emit?: (line: string) => unknown
): Promise<void>

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
