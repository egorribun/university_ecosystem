import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"
import { PageErrorBoundary } from "@/components/error/PageErrorBoundary"

const Messenger = lazy(() => import("@/pages/Messenger"))

export const Route = createFileRoute("/_auth/messenger/$chatId")({
  // Wave 128 SW2 — explicit opt-down to client-only render (W129+
  // candidate after SSR-readiness audit). Same rationale as parent
  // /messenger route: interactive WebSocket UI, no SSR benefit.
  ssr: false,
  component: () => (
    <PageErrorBoundary key="messenger">
      <Messenger />
    </PageErrorBoundary>
  ),
})
