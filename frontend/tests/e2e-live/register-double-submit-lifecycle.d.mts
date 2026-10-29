export function isOpaqueRegistrationReceipt(value: unknown): boolean

export function waitForRegistrationCompletion(
  pending: Array<Promise<boolean>>,
  timeoutMs: number
): Promise<boolean>

export function withRegistrationDetach<T>(
  action: () => Promise<T>,
  detach: () => Promise<void>,
  reportDetachFailure: () => void
): Promise<T>
