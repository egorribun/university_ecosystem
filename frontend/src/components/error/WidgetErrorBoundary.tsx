/**
 * WidgetErrorBoundary
 *
 * Silent error boundary for non-critical widgets.
 * Hides failed widgets without disrupting the user experience.
 * Logs to Sentry but shows minimal or no UI.
 *
 * @example
 * ```tsx
 * <WidgetErrorBoundary>
 *   <WeatherWidget />
 * </WidgetErrorBoundary>
 * ```
 */

import { Component, type ErrorInfo, type ReactNode } from "react"
import * as Sentry from "@sentry/react"

interface WidgetErrorBoundaryProps {
  children: ReactNode
  /** Widget name for error context */
  widgetName?: string
  /** Custom fallback (default: null - hides widget) */
  fallback?: ReactNode
  /** Whether to show any fallback (default: false) */
  showFallback?: boolean
  /** Callback when error occurs */
  onError?: (error: Error) => void
}

interface WidgetErrorBoundaryState {
  hasError: boolean
}

/** Minimal fallback for widget errors */
function WidgetPlaceholder() {
  return (
    <div className="flex h-full min-h-15 items-center justify-center rounded-lg bg-(--glass-bg)/(--opacity-medium)">
      <span className="text-xs text-text-primary/(--opacity-medium)">—</span>
    </div>
  )
}

export class WidgetErrorBoundary extends Component<
  WidgetErrorBoundaryProps,
  WidgetErrorBoundaryState
> {
  constructor(props: WidgetErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(): Partial<WidgetErrorBoundaryState> {
    return { hasError: true }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    const { widgetName, onError } = this.props

    // Report to Sentry with low severity
    Sentry.captureException(error, {
      contexts: {
        react: {
          componentStack: errorInfo.componentStack,
        },
        widget: {
          name: widgetName,
        },
      },
      tags: {
        errorBoundary: "widget",
        widget: widgetName,
      },
      level: "info", // Lowest severity - non-critical
    })

    // Call error callback
    onError?.(error)

    if (import.meta.env.DEV) {
      console.warn("[WidgetErrorBoundary]", { error, widget: widgetName })
    }
  }

  render(): ReactNode {
    if (this.state.hasError) {
      const { fallback, showFallback = false } = this.props

      // Custom fallback
      if (fallback) {
        return fallback
      }

      // Show placeholder or hide completely
      if (showFallback) {
        return <WidgetPlaceholder />
      }

      // Silent failure - render nothing
      return null
    }

    return this.props.children
  }
}

export default WidgetErrorBoundary
