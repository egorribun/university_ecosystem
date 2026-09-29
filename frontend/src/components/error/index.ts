/**
 * Error Boundaries
 *
 * Feature- and widget-level error boundaries. The page-level boundary is
 * imported directly from `@/components/error/PageErrorBoundary`.
 *
 * @example
 * ```tsx
 * import { FeatureErrorBoundary, WidgetErrorBoundary } from '@/components/error'
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

export { FeatureErrorBoundary } from "./FeatureErrorBoundary"
export { WidgetErrorBoundary } from "./WidgetErrorBoundary"
