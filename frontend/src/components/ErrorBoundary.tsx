import { Component, type ErrorInfo, type ReactNode } from "react"
import * as Sentry from "@sentry/react"
import "./ErrorBoundary.css"

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
        <div className="error-boundary">
          <div className="error-boundary__content">
            <h1 className="error-boundary__title">Что-то пошло не так</h1>
            <p className="error-boundary__message">
              Произошла непредвиденная ошибка. Мы уже работаем над её исправлением.
            </p>
            {import.meta.env.DEV && this.state.error && (
              <details className="error-boundary__details">
                <summary>Подробности ошибки</summary>
                <pre>{this.state.error.toString()}</pre>
                {this.state.errorInfo && <pre>{this.state.errorInfo.componentStack}</pre>}
              </details>
            )}
            <div className="error-boundary__actions">
              <button
                type="button"
                onClick={this.handleRetry}
                className="error-boundary__button error-boundary__button--primary"
              >
                Попробовать снова
              </button>
              <button
                type="button"
                onClick={this.handleReload}
                className="error-boundary__button error-boundary__button--secondary"
              >
                Перезагрузить страницу
              </button>
              <button
                type="button"
                onClick={this.handleGoHome}
                className="error-boundary__button error-boundary__button--secondary"
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




