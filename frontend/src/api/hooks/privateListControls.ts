/** Account-private lists own their data sources, transformations, and keys.
 * Only scheduling, error presentation, notification, and pagination controls
 * may cross the caller-options boundary, including from JavaScript callers.
 */
const CONTROL_KEYS = [
  "enabled",
  "staleTime",
  "gcTime",
  "retry",
  "retryDelay",
  "retryOnMount",
  "networkMode",
  "refetchInterval",
  "refetchIntervalInBackground",
  "refetchOnMount",
  "refetchOnReconnect",
  "refetchOnWindowFocus",
  "throwOnError",
  "notifyOnChangeProps",
  "getPreviousPageParam",
  "maxPages",
  "meta",
  "subscribed",
] as const

export type PrivateListControls<T> = Pick<T, Extract<(typeof CONTROL_KEYS)[number], keyof T>>

export const pickPrivateListControls = <T extends object>(
  options: T | undefined
): PrivateListControls<T> => {
  const controls: Record<string, unknown> = {}
  for (const key of CONTROL_KEYS) {
    const value = (options as Record<string, unknown> | undefined)?.[key]
    if (value !== undefined) controls[key] = value
  }
  return controls as PrivateListControls<T>
}
