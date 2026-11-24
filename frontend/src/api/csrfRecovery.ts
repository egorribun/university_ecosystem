/** Only the pre-handler CSRF rejection carries this first-party marker. */
export const CSRF_REJECTED_HEADER = "x-csrf-rejected"

/** Force a fresh cookie even when an older session-bound cookie is present. */
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
