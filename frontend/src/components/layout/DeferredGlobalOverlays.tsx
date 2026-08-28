import { lazy, Suspense, useEffect, useState } from "react"
import OfflineIndicator from "@/components/feedback/OfflineIndicator"
import { ensurePushMessageBridge } from "@/push/pushMessageBus"

// Keep optional global surfaces outside the first interaction window. A zero
// delay timer still runs while React/Lighthouse is hydrating the route and
// pulls three independent chunks into the same main-thread window as the
// first meaningful paint. Four seconds is long enough for the shell and
// primary route to settle, while still making the conveniences available
// quickly for a normal user. An explicit interaction promotes them sooner.
export const DEFERRED_OVERLAY_DELAY_MS = 4_000

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

/**
 * Mount optional global overlays in the first task after the initial React
 * commit. Rendering `null` on the server and on the first client render keeps
 * SSR/hydration markup identical. The timer is deliberately cleaned up so a
 * route transition or aborted document mount cannot retain work or update an
 * unmounted tree.
 */
export function DeferredGlobalOverlays() {
  const [ready, setReady] = useState(false)

  useEffect(() => {
    ensurePushMessageBridge()

    let mounted = true
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
            if (mounted) setReady(true)
          },
          { timeout: 2_000 }
        )
      } else if (mounted) {
        setReady(true)
      }
    }, DEFERRED_OVERLAY_DELAY_MS)
    let idleHandle: number | null = null

    const promoteOnInteraction = () => {
      if (!mounted) return
      if (timer !== null) {
        window.clearTimeout(timer)
        timer = null
      }
      const idleWindow = window as Window & {
        cancelIdleCallback?: (handle: number) => void
      }
      if (idleHandle !== null && typeof idleWindow.cancelIdleCallback === "function") {
        idleWindow.cancelIdleCallback(idleHandle)
        idleHandle = null
      }
      setReady(true)
    }
    const interactionEvents = ["pointerdown", "keydown", "touchstart", "focusin"] as const
    interactionEvents.forEach((eventName) =>
      window.addEventListener(eventName, promoteOnInteraction, { once: true, passive: true })
    )

    return () => {
      mounted = false
      if (timer !== null) window.clearTimeout(timer)
      const idleWindow = window as Window & {
        cancelIdleCallback?: (handle: number) => void
      }
      if (idleHandle !== null && typeof idleWindow.cancelIdleCallback === "function") {
        idleWindow.cancelIdleCallback(idleHandle)
      }
      interactionEvents.forEach((eventName) =>
        window.removeEventListener(eventName, promoteOnInteraction)
      )
    }
  }, [])

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
