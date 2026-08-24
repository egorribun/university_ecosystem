import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"
import * as v from "valibot"

import { EVENTS_PAGE_SIZE, prefetchEventsListQuery } from "@/api/hooks/events"
import { eventsSearchSchema } from "@/features/events/schema"
import { resolveLoaderLang } from "@/utils/loaderLang"

const Events = lazy(() => import("@/pages/Events"))

export const Route = createFileRoute("/_auth/events/")({
  // Wave 129 SW1 — per-route SSR enabled. Inherits `_auth.tsx` `ssr: true`
  // (per TanStack Start v1 inheritance contract; child can ONLY make MORE
  // restrictive — `false > 'data-only' > true`). Loader prefetches first
  // page of cursor-paginated events into the per-request QueryClient
  // (SsrRoot W128 SW3) so SSR HTML ships with real event content cards
  // rather than skeletons. `prefetchEventsListQuery` factory is the
  // pre-existing W128 export at `events.ts:261-272` — drop-in.
  loader: async ({ context }) => {
    // Promise.allSettled — best-effort prefetch. If backend is unreachable
    // (LHCI dev, network failures), the query throws → catch → loader
    // resolves anyway. Route still renders with skeleton placeholders;
    // client useInfiniteQuery refetches on mount. Prevents NO_FCP per
    // W128 SW3-followup lesson.
    await Promise.allSettled([
      prefetchEventsListQuery(context.queryClient, {
        language: resolveLoaderLang(),
        limit: EVENTS_PAGE_SIZE,
      }),
    ])
  },
  validateSearch: (search: Record<string, unknown>) => v.parse(eventsSearchSchema, search),
  component: Events,
})
