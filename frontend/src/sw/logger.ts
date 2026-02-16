/**
 * Unified logger for the Service Worker.
 */
export const log = (..._args: unknown[]) => {
  if (import.meta.env.DEV) {
    // Development-only logging
  }
}

export const warn = (...args: unknown[]) => {
  if (import.meta.env.DEV) {
    console.warn("[SW]", ...args)
  }
}

export const error = (...args: unknown[]) => {
  if (import.meta.env.DEV) {
    console.error("[SW]", ...args)
  }
}
