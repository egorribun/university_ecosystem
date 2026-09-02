/**
 * PageErrorBoundary
 *
 * Error boundary for page-level errors.
 * Shows a page-specific error UI with retry and navigation options.
 * Resets on route changes.
 *
 * @example
 * ```tsx
 * <Route path="/events" element={
 *   <PageErrorBoundary>
 *     <Events />
 *   </PageErrorBoundary>
 * } />
 * ```
 */

import { Component, type ErrorInfo, type ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate, useRouterState } from "@tanstack/react-router"
import * as Sentry from "@sentry/react"
import { logError } from "@/app/logger"
import { extractApiError } from "@/utils/error"

interface PageErrorBoundaryProps {
  children: ReactNode
  /** Optional page name for error context */
  pageName?: string
  /** Custom fallback component */
  fallback?: ReactNode
}

interface PageErrorBoundaryState {
  hasError: boolean
  error: Error | null
  errorInfo: ErrorInfo | null
}

/** Fallback UI for page errors */
export function PageErrorFallback({
  error,
  onRetry,
  onGoHome,
}: {
  error: Error | null
  onRetry: () => void
  onGoHome: () => void
}) {
  const { t, ready } = useTranslation(["system"])

  if (!ready) {
    return (
      <div className="flex min-h-(--h-hero-sm) items-center justify-center">
        <div className="animate-pulse">{t("common:statuses.loading")}</div>
      </div>
    )
  }

  return (
    <div
      role="alert"
      className="flex min-h-(--h-hero-sm) flex-col items-center justify-center gap-6 p-8 text-center"
    >
      <div className="max-w-[28rem]">
        <h1 className="mb-2 text-2xl font-bold text-text-primary">{t("system:pageError.title")}</h1>
        <p className="text-text-primary/(--opacity-strong)">{t("system:pageError.description")}</p>
        {import.meta.env.DEV && error && (
          <details className="mt-4 text-left">
            <summary className="cursor-pointer text-sm text-text-primary/(--opacity-medium)">
              Error details
            </summary>
            <div className="mt-2 overflow-auto rounded bg-(--glass-bg) p-3 text-left text-xs font-mono">
              {(() => {
                const apiError = extractApiError(error)
                return (
                  <div className="space-y-1">
                    <div className="font-bold text-error-text">
                      {apiError.status > 0 ? `Status: ${apiError.status}` : "Non-API Error"}
                    </div>
                    <div>{apiError.message}</div>
                    {apiError.traceId && (
                      <div className="opacity-70 text-(--fs-label-xs)">
                        Trace ID: {apiError.traceId}
                      </div>
                    )}
                    {apiError.details && apiError.details.length > 0 && (
                      <ul className="mt-2 list-inside list-disc opacity-80">
                        {apiError.details.map((d, i) => (
                          <li key={i}>
                            {d.field ? <span className="underline">{d.field}</span> : "Error"}:{" "}
                            {d.message}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )
              })()}
              <pre className="mt-3 border-t border-border-subtle pt-2 opacity-50">
                {error.stack || error.message}
              </pre>
            </div>
          </details>
        )}
      </div>
      <div className="flex gap-3">
        <button
          type="button"
          onClick={onRetry}
          className="rounded-full bg-(--primary-main) px-6 py-2 font-medium text-white transition-opacity hover:opacity-strong"
        >
          {t("system:pageError.retry")}
        </button>
        <button
          type="button"
          onClick={onGoHome}
          className="rounded-full border border-(--text-primary)/(--opacity-soft) px-6 py-2 font-medium text-text-primary transition-colors hover:bg-(--glass-bg)"
        >
          {t("system:pageError.home")}
        </button>
      </div>
    </div>
  )
}

/** Inner component that uses hooks */
function PageErrorBoundaryInner({ children, pageName, fallback }: PageErrorBoundaryProps) {
  const locationKey = useRouterState({ select: (s) => s.location.pathname })
  const navigate = useNavigate()

  return (
    <PageErrorBoundaryClass
      pageName={pageName}
      fallback={fallback}
      locationKey={locationKey}
      onNavigateHome={() => navigate({ to: "/" })}
    >
      {children}
    </PageErrorBoundaryClass>
  )
}

/** Props for the class component */
interface PageErrorBoundaryClassProps extends PageErrorBoundaryProps {
  locationKey: string
  onNavigateHome: () => void
}

/** Class component for error catching */
export class PageErrorBoundaryClass extends Component<
  PageErrorBoundaryClassProps,
  PageErrorBoundaryState
> {
  constructor(props: PageErrorBoundaryClassProps) {
    super(props)
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    }
  }

  static getDerivedStateFromError(error: Error): Partial<PageErrorBoundaryState> {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    this.setState({ errorInfo })

    // Report to Sentry with page context
    Sentry.captureException(error, {
      contexts: {
        react: {
          componentStack: errorInfo.componentStack,
        },
        page: {
          name: this.props.pageName,
        },
      },
      tags: {
        errorBoundary: "page",
        page: this.props.pageName,
      },
    })

    if (import.meta.env.DEV) {
      logError("[PageErrorBoundary]", { error, errorInfo, page: this.props.pageName })
    }
  }

  componentDidUpdate(prevProps: PageErrorBoundaryClassProps): void {
    // Reset on route change
    if (prevProps.locationKey !== this.props.locationKey && this.state.hasError) {
      this.handleReset()
    }
  }

  handleReset = (): void => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    })
  }

  handleGoHome = (): void => {
    this.handleReset()
    this.props.onNavigateHome()
  }

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }

      return (
        <PageErrorFallback
          error={this.state.error}
          onRetry={this.handleReset}
          onGoHome={this.handleGoHome}
        />
      )
    }

    return this.props.children
  }
}

export const PageErrorBoundary = PageErrorBoundaryInner
export default PageErrorBoundary
