/**
 * FeatureErrorBoundary
 *
 * Error boundary for feature-level errors.
 * Shows a compact error UI within the page without disrupting other features.
 * Supports graceful degradation with custom fallback.
 *
 * @example
 * ```tsx
 * <FeatureErrorBoundary
 *   fallback={<ScheduleUnavailable />}
 *   featureName="schedule"
 * >
 *   <ScheduleWidget />
 * </FeatureErrorBoundary>
 * ```
 */

import { Component, type ErrorInfo, type ReactNode } from "react"
import { AlertTriangle } from "lucide-react"
import * as Sentry from "@sentry/react"

interface FeatureErrorBoundaryProps {
  children: ReactNode
  /** Feature name for error context */
  featureName?: string
  /** Custom fallback when error occurs */
  fallback?: ReactNode
  /** Callback when error occurs */
  onError?: (error: Error, errorInfo: ErrorInfo) => void
  /** Whether to report to Sentry (default: true) */
  reportToSentry?: boolean
}

interface FeatureErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

/** Default fallback for feature errors */
function FeatureErrorFallback({
  onRetry,
  featureName,
}: {
  onRetry: () => void
  featureName?: string
}) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center justify-center gap-3 rounded-xl border border-(--text-primary)/(--opacity-subtle) bg-(--glass-bg) p-6 text-center"
    >
      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-warning-bg/(--opacity-dim) text-warning-text">
        <AlertTriangle className="h-5 w-5 text-warning-text" />
      </div>
      <div>
        <h3 className="text-sm font-bold text-text-primary">
          {featureName ? `${featureName} unavailable` : "Feature unavailable"}
        </h3>
        <p className="text-xs text-text-primary/(--opacity-medium)">Something went wrong</p>
      </div>
      <button type="button" onClick={onRetry} className="hover:underline">
        <span className="text-xs font-black text-(--accent)">Try again</span>
      </button>
    </div>
  )
}

export class FeatureErrorBoundary extends Component<
  FeatureErrorBoundaryProps,
  FeatureErrorBoundaryState
> {
  constructor(props: FeatureErrorBoundaryProps) {
    super(props)
    this.state = {
      hasError: false,
      error: null,
    }
  }

  static getDerivedStateFromError(error: Error): Partial<FeatureErrorBoundaryState> {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    const { featureName, onError, reportToSentry = true } = this.props

    // Report to Sentry
    if (reportToSentry) {
      Sentry.captureException(error, {
        contexts: {
          react: {
            componentStack: errorInfo.componentStack,
          },
          feature: {
            name: featureName,
          },
        },
        tags: {
          errorBoundary: "feature",
          feature: featureName,
        },
        level: "warning", // Lower severity than page errors
      })
    }

    // Call error callback
    onError?.(error, errorInfo)

    if (import.meta.env.DEV) {
      console.error("[FeatureErrorBoundary]", { error, errorInfo, feature: featureName })
    }
  }

  handleReset = (): void => {
    this.setState({
      hasError: false,
      error: null,
    })
  }

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }

      return (
        <FeatureErrorFallback onRetry={this.handleReset} featureName={this.props.featureName} />
      )
    }

    return this.props.children
  }
}

export default FeatureErrorBoundary
