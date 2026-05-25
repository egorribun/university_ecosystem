import { createFileRoute } from "@tanstack/react-router"
import { lazy, Suspense } from "react"

import { newsDetailQueryOptions } from "@/api/hooks/news"
import { FeatureErrorBoundary } from "@/components/error"
import { resolveLoaderLang } from "@/utils/loaderLang"

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
  // Wave 129 SW5 — per-route SSR enabled. Inherits `_auth.tsx` ssr:true
  // (W128 SW2). Loader pre-fetches the article body + metadata into the
  // per-request QueryClient so SSR HTML emits with NewsDetailHero +
  // NewsDetailBody content rather than a `null` Suspense fallback.
  // `newsDetailQueryOptions` is the factory extracted into hooks/news.ts
  // alongside SW5 — same queryKey shape `["news", id, language]` as the
  // pre-W129 inline useQuery, so cache entries hit identically on the
  // client side after hydration.
  loader: async ({ context, params }) => {
    // Promise.allSettled best-effort; backend-down doesn't crash the
    // loader → no NO_FCP. NewsDetail's own useQuery refetches on mount
    // with normal error handling (hard-coded 304/no-data throws are
    // swallowed by the catch since this is best-effort, not authoritative).
    await Promise.allSettled([
      context.queryClient.ensureQueryData(newsDetailQueryOptions(params.id, resolveLoaderLang())),
    ])
  },
  component: NewsDetailRoute,
})
