import type { Page } from "@playwright/test"

export type LiveRegistrationCost = 1 | 2
export type LiveRegistrationDiagnosticStage =
  | "deadline"
  | "origin"
  | "state-root"
  | "owner-read"
  | "ledger-read"
  | "quiet-wait"
  | "rolling-wait"
  | "reserve"
  | "submit"
  | "request-drain"
  | "confirm"

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

/** Internal timer seam used by deterministic request-drain deadline tests. */
export declare function waitForTrackedRequests(
  activeRequests: Readonly<{ size: number }>,
  changed: Array<() => void>,
  deadlineAtMs: number,
  options?: {
    now?: () => number
    scheduleTimer?: (callback: () => void, delayMs: number) => ReturnType<typeof setTimeout>
    clearTimer?: (timer: ReturnType<typeof setTimeout>) => void
  }
): Promise<boolean>

export declare function initializeLiveRegistrationAdmission(
  stateRoot: string,
  options?: { now?: () => number; sleep?: (milliseconds: number) => Promise<void> }
): Promise<void>

export declare function runLiveRegistrationAdmission<T>(
  page: Page,
  deadlineAtMs: number,
  cost: LiveRegistrationCost,
  action: () => Promise<T>,
  project?: "desktop" | "mobile",
  timeoutMs?: number | null
): Promise<T>

export declare function reportLiveRegistrationAdmissionFailure(
  project: "desktop" | "mobile",
  stage: LiveRegistrationDiagnosticStage,
  error: unknown,
  details?: {
    cost?: LiveRegistrationCost
    timeoutMs?: number | null
    deadlineAtMs?: number | null
    ownerPresent?: boolean
    ledgerPresent?: boolean
    requestCount?: number
    activeRequestCount?: number
    responseObserved?: boolean
    status?: number | null
    actionFailed?: boolean
  }
): void
