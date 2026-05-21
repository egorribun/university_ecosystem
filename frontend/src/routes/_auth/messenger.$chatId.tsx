import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"
import { PageErrorBoundary } from "@/components/error/PageErrorBoundary"

const Messenger = lazy(() => import("@/pages/Messenger"))

export const Route = createFileRoute("/_auth/messenger/$chatId")({
  // Wave 180 SW3 — /messenger detail SSR enabled via `ssr: 'data-only'`
  // matching parent `messenger.tsx` (list) route. Closes W134 §Honesty #10
  // for both routes together. Full rationale + W161 SW2 history retained
  // in parent route's comment block.
  //
  // Same 3-concern closure as parent (W180 SW3):
  //   (a) Query gate inconsistency → CLOSED via messagesQueryOptions
  //       factory + `enabled: !!selectedChatId` gate preserved.
  //   (b) Privacy/cache scoping → CLOSED via 'data-only' (no SSR data
  //       prefetch) + Cache-Control: no-store, private headers injected
  //       in server.ts for /messenger* paths.
  //   (c) UX/value tradeoff → ACCEPTED as-designed; 'data-only' gives
  //       shell-render LCP win without trying to pre-render
  //       WebSocket-driven message stream (which would conflict with
  //       real-time UX immediately post-hydration).
  ssr: "data-only",
  component: () => (
    <PageErrorBoundary key="messenger">
      <Messenger />
    </PageErrorBoundary>
  ),
})
