import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"
import { PageErrorBoundary } from "@/components/error/PageErrorBoundary"

const Messenger = lazy(() => import("@/pages/Messenger"))

export const Route = createFileRoute("/_auth/messenger")({
  // Wave 128 SW2 — explicit opt-down to client-only render. Parent
  // _auth.tsx now defaults to ssr:true; this route opts back to false
  // until per-route SSR-readiness audit happens (W129+). Chat is
  // interactive (WebSocket-driven) — no SSR LCP benefit anyway.
  ssr: false,
  component: () => (
    <PageErrorBoundary key="messenger">
      <Messenger />
    </PageErrorBoundary>
  ),
})
