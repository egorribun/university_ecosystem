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
import { useLocation, useNavigate } from "react-router-dom"
import * as Sentry from "@sentry/react"
import { logError } from "@/app/logger"

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
function PageErrorFallback({
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
      <div className="max-w-md">
        <h1 className="mb-2 text-2xl font-bold text-text-primary">
          {t("system:pageError.title", "Page Error")}
        </h1>
        <p className="text-text-primary/(--opacity-strong)">
          {t("system:pageError.description", "Something went wrong loading this page.")}
        </p>
        {import.meta.env.DEV && error && (
          <details className="mt-4 text-left">
            <summary className="cursor-pointer text-sm text-text-primary/(--opacity-medium)">
              Error details
            </summary>
            <pre className="mt-2 overflow-auto rounded bg-(--glass-bg) p-2 text-xs">
              {error.message}
            </pre>
          </details>
        )}
      </div>
      <div className="flex gap-3">
        <button
          type="button"
          onClick={onRetry}
          className="rounded-full bg-(--primary-main) px-6 py-2 font-medium text-white transition-opacity hover:opacity-strong"
        >
          {t("system:pageError.retry", "Try Again")}
        </button>
        <button
          type="button"
          onClick={onGoHome}
          className="rounded-full border border-(--text-primary)/(--opacity-soft) px-6 py-2 font-medium text-text-primary transition-colors hover:bg-(--glass-bg)"
        >
          {t("system:pageError.home", "Go Home")}
        </button>
      </div>
    </div>
  )
}

/** Inner component that uses hooks */
function PageErrorBoundaryInner({ children, pageName, fallback }: PageErrorBoundaryProps) {
  const location = useLocation()
  const navigate = useNavigate()

  return (
    <PageErrorBoundaryClass
      pageName={pageName}
      fallback={fallback}
      locationKey={location.key}
      onNavigateHome={() => navigate("/")}
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
class PageErrorBoundaryClass extends Component<
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
