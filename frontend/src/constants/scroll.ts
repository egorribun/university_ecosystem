/**
 * Global Scroll Constants
 */
/** Enter compact mode only after a deliberate scroll. */
export const NAVBAR_SCROLL_ENTER_THRESHOLD = 72
/** Leave compact mode below a separate threshold to prevent boundary flapping. */
export const NAVBAR_SCROLL_EXIT_THRESHOLD = 24
/** @deprecated Use the hysteresis thresholds above. */
export const NAVBAR_SCROLL_THRESHOLD = NAVBAR_SCROLL_ENTER_THRESHOLD
export const SCROLL_RESTORATION_TIMEOUT = 100
