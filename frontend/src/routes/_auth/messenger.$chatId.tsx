import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"
import { PageErrorBoundary } from "@/components/error/PageErrorBoundary"

const Messenger = lazy(() => import("@/pages/Messenger"))

export const Route = createFileRoute("/_auth/messenger/$chatId")({
  // /messenger × 2 SSR — explicit defer-by-design (W161 SW2 closure of
  // W134 §Honesty #10). Same rationale as parent `messenger.tsx` route
  // — full decision narrative there. TL;DR: chat is inherently
  // WebSocket-driven (real-time UX), chat list + counterpart names
  // expose user-private relationship state (privacy/cache scoping
  // needs design), useMessengerController query gate inconsistency
  // would surface 401-error in SSR HTML, STRICT 1-iter cap budget
  // doesn't fit factory-refactor + 2 loaders + privacy review.
  ssr: false,
  component: () => (
    <PageErrorBoundary key="messenger">
      <Messenger />
    </PageErrorBoundary>
  ),
})
