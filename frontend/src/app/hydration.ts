export const APP_HYDRATED_EVENT = "ue:app-hydrated"
export const BRAND_BOOT_LOADER_EXIT_TIMEOUT_MS = 600

const STATIC_BRAND_BOOT_LOADER_SELECTOR = "[data-brand-boot-loader]"
let staticLoaderReleaseScheduled = false

/**
 * The SSR shell renders the brand loader before `#root`, while the client
 * tree owns only the application root. React therefore cannot reliably remove
 * that static sibling after hydration (WebKit keeps it in the document). Keep
 * the hand-off in the hydration boundary so every engine gets the same
 * transition and cleanup semantics.
 */
function releaseStaticBrandBootLoader(): void {
  const loader = document.querySelector<HTMLElement>(STATIC_BRAND_BOOT_LOADER_SELECTOR)
  if (!loader || loader.closest("#root")) {
    return
  }

  loader.dataset.state = "exiting"
  loader.setAttribute("aria-busy", "false")

  let timeoutId: number | undefined
  const removeLoader = () => {
    if (timeoutId !== undefined) {
      window.clearTimeout(timeoutId)
      timeoutId = undefined
    }
    loader.removeEventListener("transitionend", removeLoader)
    // Do not remove a node that was adopted by a client-rendered root while
    // the transition was in progress.
    if (loader.isConnected && !loader.closest("#root")) {
      loader.remove()
    }
  }

  loader.addEventListener("transitionend", removeLoader, { once: true })
  timeoutId = window.setTimeout(removeLoader, BRAND_BOOT_LOADER_EXIT_TIMEOUT_MS)
}

export function markAppHydrated(): void {
  if (typeof window === "undefined" || window.__APP_HYDRATED) {
    return
  }

  window.__APP_HYDRATED = true
  window.dispatchEvent(new Event(APP_HYDRATED_EVENT))

  // `createRoot(document)` owns the static document fallback and may still
  // be committing the route tree when provider effects publish this signal.
  // Removing the sibling loader synchronously races that commit in Chromium
  // and WebKit (`NotFoundError: removeChild`). Queue the hand-off as a macrotask
  // so React has completed its current commit before we mutate the document;
  // the shared exit timeout still gives the transition deterministic cleanup.
  if (!staticLoaderReleaseScheduled) {
    staticLoaderReleaseScheduled = true
    window.setTimeout(() => {
      staticLoaderReleaseScheduled = false
      releaseStaticBrandBootLoader()
    }, 0)
  }
}
