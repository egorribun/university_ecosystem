import { lazy, Suspense, useEffect, useState } from "react"
import OfflineIndicator from "@/components/feedback/OfflineIndicator"
import { ensurePushMessageBridge } from "@/push/pushMessageBus"

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
    const timer = window.setTimeout(() => setReady(true), 0)
    return () => window.clearTimeout(timer)
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
