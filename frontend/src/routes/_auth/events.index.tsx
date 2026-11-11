import { createFileRoute } from "@tanstack/react-router"
import * as v from "valibot"

import { EVENTS_PAGE_SIZE, prefetchEventsListQuery } from "@/api/hooks/events"
import { eventsSearchSchema } from "@/features/events/schema"
import { resolveLoaderLang } from "@/utils/loaderLang"

// TanStack Start code-splits route components and preloads the matched
// route chunk before hydration, so the page is imported statically, as in
// /dashboard. A nested React.lazy suspended during hydration and React
// re-inserted the page <title>/<meta> beside the server-rendered set.
import Events from "@/pages/Events"

export const Route = createFileRoute("/_auth/events/")({
  ssr: true,
  loader: async ({ context }) => {
    // Private event lists are not transferred by the router's dashboard-only
    // hydration allowlist. Keep SSR pending instead of fetching unusable data
    // or warming an empty server projection that the client cannot reproduce.
    if (import.meta.env.SSR) return

    // Best-effort browser warmup for the default active/newest feed. The query
    // factory enforces confirmed ownership before and after its request.
    await Promise.allSettled([
      prefetchEventsListQuery(context.queryClient, {
        language: resolveLoaderLang(),
        limit: EVENTS_PAGE_SIZE,
        is_active: true,
        order: "starts_at_desc",
      }),
    ])
  },
  // The loader only warms the first feed page. Category, sort and search
  // params filter on the client, so re-running it on every search change only
  // risked the router's pending UI replacing the page (and its scroll
  // position) mid-switch; React Query owns freshness after entry.
  shouldReload: false,
  validateSearch: (search: Record<string, unknown>) => v.parse(eventsSearchSchema, search),
  component: Events,
})
