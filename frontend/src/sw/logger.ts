/**
 * Unified logger for the Service Worker.
 */
export const log = (...args: unknown[]) => {
  if (import.meta.env.DEV) {
    console.log("[SW]", ...args)
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
