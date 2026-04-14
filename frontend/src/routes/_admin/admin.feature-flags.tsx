import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"
import { PageErrorBoundary } from "@/components/error/PageErrorBoundary"

const AdminFeatureFlags = lazy(() => import("@/pages/AdminFeatureFlags"))

export const Route = createFileRoute("/_admin/admin/feature-flags")({
  component: () => (
    <PageErrorBoundary key="admin">
      <AdminFeatureFlags />
    </PageErrorBoundary>
  ),
})
