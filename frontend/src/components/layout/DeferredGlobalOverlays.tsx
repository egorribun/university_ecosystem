import { lazy, Suspense, useState, useSyncExternalStore } from "react"
import OfflineIndicator from "@/components/feedback/OfflineIndicator"
import { ensurePushMessageBridge } from "@/push/pushMessageBus"

// Keep optional global surfaces outside the first interaction window. A zero
// delay timer still runs while React/Lighthouse is hydrating the route and
// pulls three independent chunks into the same main-thread window as the
// first meaningful paint. Four seconds is long enough for the shell and
// primary route to settle, while still making the conveniences available
// quickly for a normal user. An explicit interaction promotes them sooner.
export const DEFERRED_OVERLAY_DELAY_MS = 4_000
export const DEFERRED_INTERACTION_EVENTS = [
  "pointerdown",
  "keydown",
  "touchstart",
  "focusin",
] as const
export const DEFERRED_INTERACTION_OPTIONS = { once: true, passive: true } as const

export function createMountedCommit(isMounted: () => boolean, commit: () => void) {
  return () => {
    if (isMounted()) commit()
  }
}

export function createDeferredMountLifecycle(commit: () => void) {
  let mounted = true
  return {
    commit: createMountedCommit(() => mounted, commit),
    unmount: () => {
      mounted = false
    },
  }
}

export function clearDeferredTimer(timer: number | null, clear: (handle: number) => void) {
  if (timer !== null) clear(timer)
}

export function cancelDeferredIdle(
  idleHandle: number | null,
  cancel: ((handle: number) => void) | undefined
) {
  if (idleHandle !== null && typeof cancel === "function") cancel(idleHandle)
}

// These surfaces are global conveniences, not part of the first meaningful
// paint. Keep them out of the root route's synchronous module graph so every
// route can render its primary content before loading the optional overlay
// implementations. The dynamic imports remain ordinary production imports;
// they are not gated on Lighthouse/E2E flags and therefore preserve the same
// behavior for real users.
const SearchDialog = lazy(async () => {
  const module = await import("@/components/search/SearchDialog")
  return { default: module.SearchDialog }
})
const LivePushToasts = lazy(() => import("@/components/feedback/LivePushToasts"))
const InstallPrompt = lazy(() => import("@/components/pwa/InstallPrompt"))

type DeferredOverlayStore = {
  subscribe: (listener: () => void) => () => void
  getSnapshot: () => boolean
  getServerSnapshot: () => boolean
}

function createDeferredOverlayStore(): DeferredOverlayStore {
  let ready = false
  let cleanup: (() => void) | null = null
  const listeners = new Set<() => void>()

  const notify = () => {
    for (const listener of listeners) listener()
  }

  const start = () => {
    ensurePushMessageBridge()
    const lifecycle = createDeferredMountLifecycle(() => {
      if (ready) return
      ready = true
      notify()
    })
    let timer: number | null = window.setTimeout(() => {
      timer = null
      const idleWindow = window as Window & {
        requestIdleCallback?: (callback: () => void, options?: { timeout: number }) => number
        cancelIdleCallback?: (handle: number) => void
      }
      if (typeof idleWindow.requestIdleCallback === "function") {
        idleHandle = idleWindow.requestIdleCallback(
          () => {
            idleHandle = null
            lifecycle.commit()
          },
          { timeout: 2_000 }
        )
      } else {
        lifecycle.commit()
      }
    }, DEFERRED_OVERLAY_DELAY_MS)
    let idleHandle: number | null = null

    const promoteOnInteraction = () => {
      clearDeferredTimer(timer, window.clearTimeout)
      timer = null
      const idleWindow = window as Window & {
        cancelIdleCallback?: (handle: number) => void
      }
      cancelDeferredIdle(idleHandle, idleWindow.cancelIdleCallback)
      idleHandle = null
      lifecycle.commit()
    }
    DEFERRED_INTERACTION_EVENTS.forEach((eventName) =>
      window.addEventListener(eventName, promoteOnInteraction, DEFERRED_INTERACTION_OPTIONS)
    )

    cleanup = () => {
      lifecycle.unmount()
      clearDeferredTimer(timer, window.clearTimeout)
      const idleWindow = window as Window & {
        cancelIdleCallback?: (handle: number) => void
      }
      cancelDeferredIdle(idleHandle, idleWindow.cancelIdleCallback)
      DEFERRED_INTERACTION_EVENTS.forEach((eventName) =>
        window.removeEventListener(eventName, promoteOnInteraction)
      )
      timer = null
      idleHandle = null
      cleanup = null
      ready = false
    }
  }

  const subscribe = (listener: () => void) => {
    listeners.add(listener)
    if (cleanup === null) start()
    return () => {
      listeners.delete(listener)
      if (listeners.size === 0) cleanup?.()
    }
  }

  return {
    subscribe,
    getSnapshot: () => ready,
    getServerSnapshot: () => false,
  }
}

/**
 * Mount optional global overlays in the first task after the initial React
 * commit. Rendering `null` on the server and on the first client render keeps
 * SSR/hydration markup identical. The timer is deliberately cleaned up so a
 * route transition or aborted document mount cannot retain work or update an
 * unmounted tree.
 */
export function DeferredGlobalOverlays() {
  const [store] = useState(createDeferredOverlayStore)
  const ready = useSyncExternalStore(store.subscribe, store.getSnapshot, store.getServerSnapshot)

  return (
    <>
      {/*
       * Offline/online are browser events, not a convenience overlay: the
       * listener must be mounted in the first commit. Keeping this import
       * synchronous avoids losing an offline transition that happens while
       * the optional overlay chunks are still being fetched. OfflineIndicator
       * itself renders null during SSR/its initial render, so this does not
       * add markup to the hydration contract.
       */}
      <OfflineIndicator />
      {ready ? (
        <Suspense fallback={null}>
          <SearchDialog />
          <LivePushToasts />
          <InstallPrompt />
        </Suspense>
      ) : null}
    </>
  )
}

export default DeferredGlobalOverlays
