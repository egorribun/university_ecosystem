export const TIMEOUTS = {
  /** Short duration for simple notifications (e.g. "Copied!") */
  TOAST_SHORT: 2400,
  /** Default duration for standard information toasts */
  TOAST_DEFAULT: 3000,
  /** Long duration for toasts with more text or interactions */
  TOAST_LONG: 6000,
  /** Duration to show the "Back online" indicator */
  OFFLINE_INDICATOR: 3000,
  /** Duration before clearing live region announcements */
  LIVE_REGION_CLEAR: 3000,
} as const
