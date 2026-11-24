/** Only the pre-handler CSRF rejection carries this first-party marker. */
export const CSRF_REJECTED_HEADER = "x-csrf-rejected"

/**
 * Ask the server for a CSRF cookie bound to the current session. The server
 * reissues the cookie only when the present one no longer matches; a cookie
 * that still matches is kept, and the caller replays with it.
 */
export async function forceRefreshCsrfCookie(signal?: AbortSignal): Promise<boolean> {
  if (typeof window === "undefined" || typeof document === "undefined") return false
  if (import.meta.env.VITE_LHCI === "true" || signal?.aborted) return false

  const controller = new AbortController()
  const abort = () => controller.abort()
  signal?.addEventListener("abort", abort, { once: true })
  const timeout = setTimeout(abort, 8_000)
  try {
    const response = await fetch("/api/v1/auth/csrf-cookie", {
      method: "GET",
      mode: "same-origin",
      credentials: "include",
      cache: "no-store",
      redirect: "error",
      headers: { "X-Requested-With": "XMLHttpRequest" },
      signal: controller.signal,
    })
    return response.ok && !controller.signal.aborted
  } catch {
    return false
  } finally {
    clearTimeout(timeout)
    signal?.removeEventListener("abort", abort)
  }
}
