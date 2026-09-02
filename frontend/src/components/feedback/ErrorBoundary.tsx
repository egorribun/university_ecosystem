import { Component, type ErrorInfo, type ReactNode } from "react"
import * as Sentry from "@sentry/react"
import { withTranslation, type WithTranslation } from "react-i18next"
import { logError } from "@/app/logger"

interface ErrorBoundaryProps extends WithTranslation {
  children: ReactNode
  fallback?: ReactNode
  onError?: (error: Error, errorInfo: ErrorInfo) => void
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
  errorInfo: ErrorInfo | null
}

export const ERROR_BOUNDARY_RADIAL_BACKGROUND =
  "radial-gradient(circle at 50% 50%, color-mix(in_srgb, var(--primary-main) var(--opacity-subtle), transparent) 0%, transparent 70%)"
export const ERROR_BOUNDARY_DETAIL_BACKGROUND = "rgb(0 0 0 / var(--opacity-faint))"

export const createErrorBoundaryInitialState = () => ({
  hasError: false,
  error: null,
  errorInfo: null,
})

/**
 * Error boundary component that catches JavaScript errors anywhere in the
 * child component tree, logs them to Sentry, and displays a fallback UI.
 */
export class ErrorBoundaryInner extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = createErrorBoundaryInitialState()
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    this.setState({ errorInfo })

    // Report to Sentry
    Sentry.captureException(error, {
      contexts: {
        react: {
          componentStack: errorInfo.componentStack,
        },
      },
    })

    // Call optional error handler
    this.props.onError?.(error, errorInfo)

    // Log to console in development
    if (import.meta.env.DEV) {
      logError("ErrorBoundary caught an error:", { error, errorInfo })
    }
  }

  handleRetry = (): void => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    })
  }

  handleReload = (): void => {
    window.location.reload()
  }

  handleGoHome = (): void => {
    window.location.href = "/"
  }

  render(): ReactNode {
    const { t } = this.props

    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }

      return (
        <div className="relative flex min-h-(--min-h-hero-sm) items-center justify-center overflow-hidden bg-page px-fluid-x">
          {/* Ambient radial glow */}
          <div
            className="pointer-events-none absolute inset-0"
            style={{
              backgroundImage: ERROR_BOUNDARY_RADIAL_BACKGROUND,
            }}
          />

          <div className="relative z-deep w-full max-w-(--layout-max-modal) rounded-2xl border border-border-subtle bg-(--bg-surface) p-10 text-center shadow-premium backdrop-blur-md">
            <h1 className="mb-4 text-3xl font-black tracking-tight text-(--text-primary)">
              {t("system:errorBoundary.title")}
            </h1>
            <p className="mb-8 text-base leading-relaxed text-(--text-secondary)">
              {t("system:errorBoundary.description")}
            </p>
            {import.meta.env.DEV && this.state.error && (
              <details className="mb-8 rounded-lg border border-border-subtle bg-(--bg-surface-hover) p-4 text-left">
                <summary className="cursor-pointer text-sm font-semibold text-(--text-tertiary)">
                  {t("system:errorBoundary.details")}
                </summary>
                <pre
                  className="mt-4 overflow-x-auto whitespace-pre-wrap wrap-break-word rounded-md border border-error-text p-3 text-xs text-error-text"
                  style={{ backgroundColor: ERROR_BOUNDARY_DETAIL_BACKGROUND }}
                >
                  {this.state.error.toString()}
                </pre>
                {this.state.errorInfo && (
                  <pre
                    className="mt-2 overflow-x-auto whitespace-pre-wrap wrap-break-word rounded-md border border-error-text p-3 text-xs text-error-text"
                    style={{ backgroundColor: ERROR_BOUNDARY_DETAIL_BACKGROUND }}
                  >
                    {this.state.errorInfo.componentStack}
                  </pre>
                )}
              </details>
            )}
            <div className="flex flex-col gap-3 sm:flex-row sm:justify-center">
              <button
                type="button"
                onClick={this.handleRetry}
                className="rounded-xl bg-(--primary-main) px-(--space-6) py-(--space-35) text-base font-extrabold text-(--text-inverse) shadow-glass transition-all duration-slow hover:-translate-y-0.5 hover:bg-(--primary-hover) hover:shadow-premium-lift active:scale-95"
              >
                {t("system:errorBoundary.retry")}
              </button>
              <button
                type="button"
                onClick={this.handleReload}
                className="rounded-xl border border-border-subtle bg-(--bg-surface-hover) px-(--space-6) py-(--space-35) text-base font-extrabold text-text-primary transition-all duration-slow hover:-translate-y-0.5 hover:bg-(--bg-surface-raised) active:scale-95"
              >
                {t("system:errorBoundary.reload")}
              </button>
              <button
                type="button"
                onClick={this.handleGoHome}
                className="rounded-xl border border-border-subtle bg-(--bg-surface-hover) px-(--space-6) py-(--space-35) text-base font-extrabold text-text-primary transition-all duration-slow hover:-translate-y-0.5 hover:bg-(--bg-surface-raised) active:scale-95"
              >
                {t("system:errorBoundary.goHome")}
              </button>
            </div>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}

export const ErrorBoundary = withTranslation()(ErrorBoundaryInner)

export default ErrorBoundary
