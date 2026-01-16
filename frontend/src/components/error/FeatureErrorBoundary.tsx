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
      className="flex flex-col items-center justify-center gap-3 rounded-xl border border-[color:var(--page-text)]/10 bg-[color:var(--glass-bg)] p-6 text-center"
    >
      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-amber-500/20">
        <svg
          className="h-5 w-5 text-amber-400"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
          />
        </svg>
      </div>
      <div>
        <p className="text-sm font-medium text-[color:var(--page-text)]">
          {featureName ? `${featureName} unavailable` : "Feature unavailable"}
        </p>
        <p className="text-xs text-[color:var(--page-text)]/60">Something went wrong</p>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="text-sm font-medium text-[color:var(--accent)] hover:underline"
      >
        Try again
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
