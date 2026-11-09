export declare const REGISTRATION_STEP_ORDER: readonly [
  "navigated",
  "hydrated",
  "filled",
  "cleanup-registered",
  "listener-attached",
  "submitted",
  "receipt-verified",
  "logged-in",
  "identity-verified",
  "page-closed",
]

export declare function registrationTraceViolations(
  trace: readonly string[],
  postCount: number
): string[]
