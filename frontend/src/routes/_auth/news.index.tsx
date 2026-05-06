import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"
import * as v from "valibot"

import { NEWS_PAGE_SIZE, prefetchNewsListQuery } from "@/api/hooks/news"
import { newsSearchSchema } from "@/features/news/schema"
import { resolveLoaderLang } from "@/utils/loaderLang"

const News = lazy(() => import("@/pages/News"))

export const Route = createFileRoute("/_auth/news/")({
  // Wave 129 SW4 — per-route SSR enabled. Inherits `_auth.tsx` ssr:true
  // (W128 SW2). Loader prefetches first page of cursor-paginated news
  // articles into per-request QueryClient (SsrRoot W128 SW3) so SSR
  // HTML ships with real article cards rather than skeletons. News is
  // content-heavy + prime SSR candidate (high traffic, SEO-relevant).
  // `prefetchNewsListQuery` factory added in SW3 mirrors events.ts:
  // 261-272 pattern — same cursor pagination shape so SSR + client
  // paths share queryKey identity.
  loader: async ({ context }) => {
    // Promise.allSettled — best-effort prefetch (W128 SW3-followup
    // NO_FCP guard). If backend is unreachable the route still renders
    // skeletons; client useInfiniteQuery refetches on mount.
    await Promise.allSettled([
      prefetchNewsListQuery(context.queryClient, {
        language: resolveLoaderLang(),
        limit: NEWS_PAGE_SIZE,
      }),
    ])
  },
  validateSearch: (search: Record<string, unknown>) => v.parse(newsSearchSchema, search),
  component: News,
})
