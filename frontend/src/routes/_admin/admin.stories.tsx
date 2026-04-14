import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"
import { PageErrorBoundary } from "@/components/error/PageErrorBoundary"

const StoriesAdmin = lazy(() => import("@/pages/StoriesAdmin"))

export const Route = createFileRoute("/_admin/admin/stories")({
  component: () => (
    <PageErrorBoundary key="admin">
      <StoriesAdmin />
    </PageErrorBoundary>
  ),
})
