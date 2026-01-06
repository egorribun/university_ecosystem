/**
 * Unified logger for the Service Worker.
 */
export const log = (...args: unknown[]) => {
  if (import.meta.env.DEV) {
    console.log("[SW]", ...args);
  }
};

export const warn = (...args: unknown[]) => {
  console.warn("[SW]", ...args);
};

export const error = (...args: unknown[]) => {
  console.error("[SW]", ...args);
};
