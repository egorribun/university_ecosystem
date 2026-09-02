export type IdleScheduler = (callback: IdleRequestCallback, options: IdleRequestOptions) => number

/**
 * requestIdleCallback is not available in Safari and older embedded browsers.
 * Keep the fallback deadline-compatible so deferred work observes the same
 * contract regardless of which scheduler the runtime provides.
 */
export const scheduleIdleFallback: IdleScheduler = (callback, options) =>
  window.setTimeout(
    () =>
      callback({
        didTimeout: true,
        timeRemaining: () => 0,
      }),
    options.timeout
  )

export function getIdleScheduler(): IdleScheduler {
  if (typeof window.requestIdleCallback === "function") {
    return window.requestIdleCallback.bind(window)
  }
  return scheduleIdleFallback
}
