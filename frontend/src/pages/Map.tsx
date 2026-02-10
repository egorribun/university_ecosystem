import { Suspense, lazy } from "react"
import Layout from "../components/Layout"
import PageFadeIn from "../components/PageFadeIn"
import { Skeleton } from "@/components/ui"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"

const MapContent = lazy(() => import("./MapContent"))

function MapSkeleton() {
  const isMobile = useMediaQuery(`(max-width: ${breakpoints.content})`)
  const iconSize = isMobile ? 26 : 34

  return (
    <div className="w-full bg-(--bg-surface) text-(--text-primary) rounded-none shadow-2xl overflow-hidden relative">
      <div className="map-page bg-(--bg-canvas-light) dark:bg-(--bg-canvas-dark) relative h-full w-full">
        <div className="glass glass--panel glass--sheen map-head flex items-center justify-between px-6 py-4 absolute top-0 left-0 right-0 z-(--z-navbar)">
          <div className="flex items-center gap-3">
            <Skeleton className={`rounded-full h-[${iconSize}px] w-[${iconSize}px]`} />
            <Skeleton className={isMobile ? "h-8 w-40" : "h-10 w-60"} />
          </div>
          <div className="flex items-center gap-2">
            <Skeleton className="h-10 w-10 rounded-xl" />
            <Skeleton className="h-10 w-10 rounded-xl" />
          </div>
        </div>

        <Skeleton className="absolute inset-0 w-full h-full z-base" />

        <div className="absolute inset-0 z-(--z-sidebar) grid place-items-center bg-background/90 backdrop-blur-sm">
          <Skeleton className="h-16 w-16 rounded-full" />
        </div>

        <div className="map-controls-shield absolute inset-0 pointer-events-none" />

        <div className="absolute bottom-8 left-1/2 -translate-x-1/2 z-(--z-navbar) pointer-events-none flex flex-col gap-3 pb-(--safe-area-bottom)">
          <div className="flex items-center gap-2 pointer-events-auto">
            <div className="glass glass--panel rounded-2xl p-1 bg-(--bg-surface)/40 backdrop-blur-xl border border-glass-border shadow-2xl flex items-center gap-1">
              <Skeleton className={isMobile ? "h-8 w-36" : "h-10 w-52"} />
              <Skeleton className="h-10 w-10 rounded-xl" />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function MapPage() {
  return (
    <Layout>
      <PageFadeIn>
        <Suspense fallback={<MapSkeleton />}>
          <MapContent />
        </Suspense>
      </PageFadeIn>
    </Layout>
  )
}




