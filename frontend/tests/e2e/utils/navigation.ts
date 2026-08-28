import type { Page } from "@playwright/test"

type GotoOptions = Parameters<Page["goto"]>[1]

const TRANSIENT_NAVIGATION_ERROR =
  /(?:NS_BINDING_ABORTED|net::ERR_ABORTED|net::ERR_CONNECTION_RESET|Frame load interrupted|WebKitErrorDomain|WebKitErrorCannotShowURL|Execution context was destroyed|navigation .* interrupted by another navigation|interrupted by another navigation)/i
const MAX_ATTEMPTS = 3

/**
 * Retry only browser-level navigation cancellations that are safe to repeat.
 * Firefox reports a competing-document navigation as NS_BINDING_ABORTED, Chromium
 * reports net::ERR_ABORTED, and WebKit reports "Frame load interrupted" while
 * the preview server and the client router are settling after an auth redirect.
 * Application errors and server responses are deliberately not swallowed.
 */
export async function gotoWithTransientRetry(
  page: Page,
  url: string,
  options?: GotoOptions
): Promise<Awaited<ReturnType<Page["goto"]>>> {
  let lastError: unknown

  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
    try {
      return await page.goto(url, options)
    } catch (error) {
      lastError = error
      const message = error instanceof Error ? error.message : String(error)
      if (!TRANSIENT_NAVIGATION_ERROR.test(message) || attempt === MAX_ATTEMPTS) {
        throw error
      }

      // Give the cancelled document and the preview connection one bounded
      // event-loop turn before retrying the same deterministic destination.
      await page.waitForTimeout(250 * attempt)
    }
  }

  // The loop either returns or throws. Keep a defensive error for type/runtime
  // completeness if the loop is changed in the future.
  throw lastError instanceof Error ? lastError : new Error(String(lastError))
}
