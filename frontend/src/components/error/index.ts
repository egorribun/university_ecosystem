/**
 * Error Boundaries
 *
 * Hierarchical error boundary components for different levels of the app.
 *
 * @example
 * ```tsx
 * import { PageErrorBoundary, FeatureErrorBoundary, WidgetErrorBoundary } from '@/components/error'
 *
 * // Page level - shows page error with navigation
 * <PageErrorBoundary pageName="Events">
 *   <Events />
 * </PageErrorBoundary>
 *
 * // Feature level - shows compact error with retry
 * <FeatureErrorBoundary featureName="Schedule">
 *   <ScheduleWidget />
 * </FeatureErrorBoundary>
 *
 * // Widget level - silently hides failed widget
 * <WidgetErrorBoundary widgetName="Weather">
 *   <WeatherWidget />
 * </WidgetErrorBoundary>
 * ```
 */

export { PageErrorBoundary, default as PageErrorBoundaryDefault } from "./PageErrorBoundary"
export { FeatureErrorBoundary } from "./FeatureErrorBoundary"
export { WidgetErrorBoundary } from "./WidgetErrorBoundary"

// Re-export existing app-level boundary
export { ErrorBoundary as AppErrorBoundary } from "@/app/ErrorBoundary"




