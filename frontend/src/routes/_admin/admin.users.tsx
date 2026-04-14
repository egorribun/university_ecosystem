import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"
import { PageErrorBoundary } from "@/components/error/PageErrorBoundary"

const AdminUsers = lazy(() => import("@/pages/AdminUsers"))

export const Route = createFileRoute("/_admin/admin/users")({
  component: () => (
    <PageErrorBoundary key="admin">
      <AdminUsers />
    </PageErrorBoundary>
  ),
})
