import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"
import { PageErrorBoundary } from "@/components/error/PageErrorBoundary"

const AdminAudit = lazy(() => import("@/pages/AdminAudit"))

export const Route = createFileRoute("/_admin/admin/audit")({
  component: () => (
    <PageErrorBoundary key="admin">
      <AdminAudit />
    </PageErrorBoundary>
  ),
})
