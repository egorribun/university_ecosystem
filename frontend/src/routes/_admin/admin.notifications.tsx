import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"
import { PageErrorBoundary } from "@/components/error/PageErrorBoundary"

const AdminNotifications = lazy(() => import("@/pages/AdminNotifications"))

export const Route = createFileRoute("/_admin/admin/notifications")({
  component: () => (
    <PageErrorBoundary key="admin">
      <AdminNotifications />
    </PageErrorBoundary>
  ),
})
