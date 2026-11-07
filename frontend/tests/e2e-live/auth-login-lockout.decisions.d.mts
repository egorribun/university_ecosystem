export interface LockoutRule {
  attempts: number
  seconds: number
}

export declare const DEFAULT_AUTH_LOCKOUT_THRESHOLDS: string
export declare function parseLockoutThresholds(value: string): LockoutRule[]
export declare function firstLockoutRule(value?: string): LockoutRule
export declare function expectedFailedAttemptStatus(attempt: number, rule: LockoutRule): 401 | 423
export declare function isAccountLockedStatus(status: number): boolean
export declare function lockoutRetryAfterWithinRule(
  headerValue: string | undefined,
  rule: LockoutRule
): boolean
