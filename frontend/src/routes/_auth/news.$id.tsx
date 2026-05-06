import { createFileRoute } from "@tanstack/react-router"
import { lazy, Suspense } from "react"
import { FeatureErrorBoundary } from "@/components/error"

const NewsDetail = lazy(() => import("@/pages/NewsDetail"))

function NewsDetailRoute() {
  return (
    <FeatureErrorBoundary featureName="news-detail">
      <Suspense fallback={null}>
        <NewsDetail />
      </Suspense>
    </FeatureErrorBoundary>
  )
}

export const Route = createFileRoute("/_auth/news/$id")({
  // Wave 128 SW2 — explicit opt-down (W129+ candidate after audit).
  ssr: false,
  component: NewsDetailRoute,
})
