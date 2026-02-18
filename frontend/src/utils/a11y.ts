/**
 * Accessibility utilities for WCAG 2.1 AA compliance.
 *
 * Provides helpers for focus management, screen reader announcements,
 * and reduced motion preferences.
 */

/**
 * Announce a message to screen readers.
 */
export function announce(message: string, priority: "polite" | "assertive" = "polite"): void {
  const container = getOrCreateAnnouncer(priority)
  container.textContent = ""
  // Force reflow for screen reader to pick up change
  void container.offsetHeight
  container.textContent = message
}

/**
 * Get or create the live region container.
 */
function getOrCreateAnnouncer(priority: "polite" | "assertive"): HTMLDivElement {
  const id = `sr-announcer-${priority}`
  let container = document.getElementById(id) as HTMLDivElement | null

  if (!container) {
    container = document.createElement("div")
    container.id = id
    container.setAttribute("role", "status")
    container.setAttribute("aria-live", priority)
    container.setAttribute("aria-atomic", "true")
    container.style.cssText = `
      position: absolute;
      width: 0.0625rem;
      height: 0.0625rem;
      padding: 0;
      margin: -0.0625rem;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    `
    document.body.appendChild(container)
  }

  return container
}

/**
 * Focus trap management for modals and dialogs.
 */
export class FocusTrap {
  private container: HTMLElement
  private previouslyFocused: Element | null = null
  private firstFocusable: HTMLElement | null = null
  private lastFocusable: HTMLElement | null = null

  constructor(container: HTMLElement) {
    this.container = container
    this.handleKeyDown = this.handleKeyDown.bind(this)
  }

  activate(): void {
    this.previouslyFocused = document.activeElement
    this.updateFocusableElements()

    document.addEventListener("keydown", this.handleKeyDown)

    // Focus first focusable element
    if (this.firstFocusable) {
      this.firstFocusable.focus()
    }
  }

  deactivate(): void {
    document.removeEventListener("keydown", this.handleKeyDown)

    // Return focus to previously focused element
    if (this.previouslyFocused instanceof HTMLElement) {
      this.previouslyFocused.focus()
    }
  }

  private updateFocusableElements(): void {
    const focusableSelectors = [
      "button:not([disabled])",
      "a[href]",
      "input:not([disabled])",
      "select:not([disabled])",
      "textarea:not([disabled])",
      '[tabindex]:not([tabindex="-1"])',
    ].join(", ")

    const focusable = Array.from(
      this.container.querySelectorAll<HTMLElement>(focusableSelectors)
    ).filter((el) => el.offsetParent !== null)

    this.firstFocusable = focusable[0] || null
    this.lastFocusable = focusable[focusable.length - 1] || null
  }

  private handleKeyDown(event: KeyboardEvent): void {
    if (event.key !== "Tab") return

    this.updateFocusableElements()

    if (!this.firstFocusable || !this.lastFocusable) return

    if (event.shiftKey) {
      if (document.activeElement === this.firstFocusable) {
        event.preventDefault()
        this.lastFocusable.focus()
      }
    } else {
      if (document.activeElement === this.lastFocusable) {
        event.preventDefault()
        this.firstFocusable.focus()
      }
    }
  }
}

/**
 * Check if user prefers reduced motion.
 */
export function prefersReducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches
}

/**
 * Subscribe to reduced motion preference changes.
 */
export function onReducedMotionChange(callback: (prefersReduced: boolean) => void): () => void {
  const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)")

  const handler = (event: MediaQueryListEvent) => {
    callback(event.matches)
  }

  mediaQuery.addEventListener("change", handler)
  return () => mediaQuery.removeEventListener("change", handler)
}

/**
 * Generate a unique ID for accessibility associations.
 */
let idCounter = 0
export function generateId(prefix = "a11y"): string {
  return `${prefix}-${++idCounter}`
}

/**
 * Skip link component helper - returns focus to main content.
 */
export function skipToMainContent(): void {
  const main = document.querySelector("main") || document.querySelector('[role="main"]')
  if (main instanceof HTMLElement) {
    main.tabIndex = -1
    main.focus()
    main.removeAttribute("tabindex")
  }
}

export default {
  announce,
  FocusTrap,
  prefersReducedMotion,
  onReducedMotionChange,
  generateId,
  skipToMainContent,
}
