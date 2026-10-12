import type { Page } from "@playwright/test"

export type LiveRegistrationCost = 1 | 2

export declare const REGISTRATION_WINDOW_MS: number
export declare const REGISTRATION_CADENCE_MS: number
export declare const REGISTRATION_MAX_COST: number
export declare const REGISTRATION_MAX_TEST_TIMEOUT_MS: number
export declare const REGISTRATION_UNKNOWN_DRAIN_MS: number

export declare function resolveLiveRegistrationStateRoot(
  environment?: Record<string, string | undefined>,
  liveWorktreeRoot?: string,
  platform?: string
): string

export declare function validateRegistrationLedger(
  value: unknown,
  ownerBinding: string,
  nowMs?: number
): {
  version: 1
  ownerBinding: string
  updatedAtMs: number
  pending: { startedAtMs: number; cost: 0 | 1 | 2 } | null
  events: { completedAtMs: number; cost: 1 | 2 }[]
}

export declare function computeRegistrationWaitMs(
  events: { completedAtMs: number; cost: 1 | 2 }[],
  cost: LiveRegistrationCost,
  nowMs?: number
): number

export declare function readPlaywrightTestSlotDeadlineAtMs(
  testInfo: unknown,
  maximumTimeoutMs?: number,
  sampleClockPair?: () => {
    localBeforeMs: number
    playwrightNowMs: number
    localAfterMs: number
  } | null
): number | null

export declare function assertRegistrationWaitFits(
  waitMs: number,
  deadlineAtMs: number,
  nowMonotonicMs?: number
): number

export declare function initializeLiveRegistrationAdmission(
  stateRoot: string,
  options?: { now?: () => number; sleep?: (milliseconds: number) => Promise<void> }
): Promise<void>

export declare function runLiveRegistrationAdmission<T>(
  page: Page,
  deadlineAtMs: number,
  cost: LiveRegistrationCost,
  action: () => Promise<T>
): Promise<T>
