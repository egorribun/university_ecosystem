/**
 * Admin Feature
 *
 * Handles admin panels: users, audit, notifications, feature flags.
 *
 * Wave 164 SW2 — features/admin/ structure migration (W150 §Honesty #1).
 * Mirror of W112 SW2 Activity orchestrator pattern: page-level files
 * (`@/pages/Admin*.tsx`) are thin <Layout><FeatureErrorBoundary> wrappers;
 * the Feature orchestrators here own content + state.
 */

// Feature orchestrators (Wave 164 SW2)
export { AdminUsersFeature } from "./AdminUsersFeature"
export { AdminFeatureFlagsFeature } from "./AdminFeatureFlagsFeature"
export { AdminAuditFeature } from "./AdminAuditFeature"
export { AdminNotificationsFeature } from "./AdminNotificationsFeature"

// Decorative backdrop (Wave 150 SW1; rendered by routes/_admin.tsx layout)
export { AdminBackdrop } from "./components/AdminBackdrop"

// API
export * from "@/api/notifications"
