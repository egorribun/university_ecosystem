import type { Page } from "@playwright/test"

export type PushProviderProbeCase = "topics" | "chat" | "reply"
export type PushProviderProbeResult = "sent" | "gone" | "failed" | "rate-limited" | "unavailable"

export function classifyProbeResponse(status: number, body: unknown): PushProviderProbeResult
export function rateLimitWaitMs(body: unknown): number
export function formatResubscribeLine(record: {
  project: string
  retry: number
  probeCase: string
}): string | null
export function requireProviderAcceptedSubscription(options: {
  adminPage: Page
  recipientPage: Page
  recipientId: string
  endpoint: string
  project: string
  retry: number
  probeCase: PushProviderProbeCase
  resubscribe: () => Promise<string>
  emit?: (line: string) => unknown
}): Promise<{ endpoint: string; resubscribed: boolean }>
export function resubscribeThroughPushSwitch(
  page: Page,
  openPushSettings: (page: Page) => Promise<void>,
  timeoutMs: number
): Promise<string>
