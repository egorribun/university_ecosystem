import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"
import { PageErrorBoundary } from "@/components/error/PageErrorBoundary"

const Messenger = lazy(() => import("@/pages/Messenger"))

export const Route = createFileRoute("/_auth/messenger/$chatId")({
  component: () => (
    <PageErrorBoundary key="messenger">
      <Messenger />
    </PageErrorBoundary>
  ),
})
