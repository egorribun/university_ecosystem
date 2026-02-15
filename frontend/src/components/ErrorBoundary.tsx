import { Component, type ErrorInfo, type ReactNode } from "react"
import * as Sentry from "@sentry/react"

interface ErrorBoundaryProps {
  children: ReactNode
  fallback?: ReactNode
  onError?: (error: Error, errorInfo: ErrorInfo) => void
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
  errorInfo: ErrorInfo | null
}

/**
 * Error boundary component that catches JavaScript errors anywhere in the
 * child component tree, logs them to Sentry, and displays a fallback UI.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    }
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
      console.error("ErrorBoundary caught an error:", error, errorInfo)
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
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }

      return (
        <div className="relative flex min-h-dvh items-center justify-center overflow-hidden bg-(--bg-page) px-fluid-x">
          {/* Ambient radial glow */}
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,color-mix(in_srgb,var(--primary-main)_var(--opacity-subtle),transparent)_0%,transparent_70%)]" />

          <div className="relative z-deep w-full max-w-(--layout-max-modal) rounded-2xl border border-border-subtle bg-(--bg-surface) p-10 text-center shadow-premium backdrop-blur-md">
            <h1 className="mb-4 text-3xl font-black tracking-tight text-(--text-primary)">
              Что-то пошло не так
            </h1>
            <p className="mb-8 text-base leading-relaxed text-(--text-secondary)">
              Произошла непредвиденная ошибка. Мы уже работаем над её исправлением.
            </p>
            {import.meta.env.DEV && this.state.error && (
              <details className="mb-8 rounded-lg border border-border-subtle bg-(--bg-surface-hover) p-4 text-left">
                <summary className="cursor-pointer text-sm font-semibold text-(--text-tertiary)">
                  Подробности ошибки
                </summary>
                <pre className="mt-4 overflow-x-auto whitespace-pre-wrap wrap-break-word rounded-md border border-error-text bg-black/(--opacity-faint) p-3 text-xs text-error-text">
                  {this.state.error.toString()}
                </pre>
                {this.state.errorInfo && (
                  <pre className="mt-2 overflow-x-auto whitespace-pre-wrap wrap-break-word rounded-md border border-error-text bg-black/(--opacity-faint) p-3 text-xs text-error-text">
                    {this.state.errorInfo.componentStack}
                  </pre>
                )}
              </details>
            )}
            <div className="flex flex-col gap-3 sm:flex-row sm:justify-center">
              <button
                type="button"
                onClick={this.handleRetry}
                className="rounded-xl bg-(--primary-main) px-6 py-3.5 text-base font-extrabold text-(--text-inverse) shadow-glass transition-all duration-slow hover:-translate-y-0.5 hover:bg-(--primary-hover) hover:shadow-premium-lift active:scale-95"
              >
                Попробовать снова
              </button>
              <button
                type="button"
                onClick={this.handleReload}
                className="rounded-xl border border-border-subtle bg-(--bg-surface-hover) px-6 py-3.5 text-base font-extrabold text-(--text-primary) transition-all duration-slow hover:-translate-y-0.5 hover:bg-(--bg-surface-raised) active:scale-95"
              >
                Перезагрузить страницу
              </button>
              <button
                type="button"
                onClick={this.handleGoHome}
                className="rounded-xl border border-border-subtle bg-(--bg-surface-hover) px-6 py-3.5 text-base font-extrabold text-(--text-primary) transition-all duration-slow hover:-translate-y-0.5 hover:bg-(--bg-surface-raised) active:scale-95"
              >
                На главную
              </button>
            </div>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}

export default ErrorBoundary
