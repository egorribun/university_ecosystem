import { Suspense, lazy } from "react"
import "@/styles/tokens/map.css"
import Layout from "@/components/Layout"
import PageFadeIn from "@/components/motion/PageFadeIn"
import { Skeleton } from "@/components/ui"
import { FeatureErrorBoundary } from "@/components/error/FeatureErrorBoundary"

const MapFeature = lazy(() =>
  import("@/features/map/MapFeature").then((m) => ({ default: m.MapFeature }))
)

function MapSkeleton() {
  return (
    <div className="map-theme aurora-mesh relative w-full py-6 sm:py-8 md:py-10 px-4 sm:px-6 md:px-10 lg:px-14">
      {/* Header skeleton */}
      <div className="flex items-center gap-4 mb-8">
        <Skeleton className="hidden sm:block h-14 w-14 rounded-xl" />
        <div className="space-y-2">
          <Skeleton className="h-10 w-64" />
          <Skeleton className="h-5 w-96" />
        </div>
      </div>

      {/* Map viewport skeleton */}
      <Skeleton className="map-viewport w-full rounded-xl" />
    </div>
  )
}

export default function MapPage() {
  return (
    <Layout>
      <PageFadeIn>
        {/* Wave 112 — wrap MapLibre GL in FeatureErrorBoundary so a runtime
            error inside the heavy 3D renderer doesn't crash the navbar/layout. */}
        <FeatureErrorBoundary featureName="map">
          <Suspense fallback={<MapSkeleton />}>
            <MapFeature />
          </Suspense>
        </FeatureErrorBoundary>
      </PageFadeIn>
    </Layout>
  )
}
