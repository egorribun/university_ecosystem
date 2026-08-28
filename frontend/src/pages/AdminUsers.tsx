import "@/styles/tokens/admin.css"
import Layout from "@/components/Layout"
import { FeatureErrorBoundary } from "@/components/error/FeatureErrorBoundary"
import { AdminUsersFeature } from "@/features/admin"

/**
 * AdminUsers page — Wave 164 SW2 thin wrapper.
 *
 * Mirror of `pages/Activity.tsx` (W112 SW2): the page owns the <Layout>
 * chrome, the feature owns content + state. FeatureErrorBoundary isolates a
 * renderer crash from the global navbar. Default export preserved at the
 * pre-W164 path + name so route lazy-imports and unit tests resolve without
 * changes.
 */
export default function AdminUsers() {
  return (
    <Layout>
      <FeatureErrorBoundary featureName="admin-users">
        <AdminUsersFeature />
      </FeatureErrorBoundary>
    </Layout>
  )
}
