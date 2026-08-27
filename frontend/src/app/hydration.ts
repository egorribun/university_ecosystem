export const APP_HYDRATED_EVENT = "ue:app-hydrated"
export const BRAND_BOOT_LOADER_EXIT_TIMEOUT_MS = 600

const STATIC_BRAND_BOOT_LOADER_SELECTOR = "[data-brand-boot-loader]"
let staticLoaderReleaseScheduled = false

/**
 * The current SSR shell renders the brand loader inside `#root`, where the
 * client tree owns its lifecycle. The legacy sibling cleanup remains as a
 * defensive compatibility path for previously cached shells; it never mutates
 * a loader that React owns inside the application root.
 */
function releaseStaticBrandBootLoader(): void {
  const loader = document.querySelector<HTMLElement>(STATIC_BRAND_BOOT_LOADER_SELECTOR)
  if (!loader || loader.closest("#root")) {
    return
  }

  loader.dataset.state = "exiting"
  loader.setAttribute("aria-busy", "false")

  // Initialise with the browser's harmless no-op timer id so a synchronous
  // test/runtime callback cannot observe an uninitialised handle.
  let timeoutId = 0
  const removeLoader = () => {
    window.clearTimeout(timeoutId)
    timeoutId = 0
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

  // A cached shell from an older build may still contain a loader sibling
  // outside `#root`. Queue that legacy hand-off as a macrotask so React has
  // completed its current commit before we mutate the document; the current
  // in-root loader is ignored by `releaseStaticBrandBootLoader` and exits via
  // its own React state transition.
  if (!staticLoaderReleaseScheduled) {
    staticLoaderReleaseScheduled = true
    window.setTimeout(() => {
      staticLoaderReleaseScheduled = false
      releaseStaticBrandBootLoader()
    }, 0)
  }
}
