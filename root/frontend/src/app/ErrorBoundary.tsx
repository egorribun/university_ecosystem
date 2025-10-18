import { Component, type ErrorInfo, type ReactNode } from "react"
import { useTranslation } from "react-i18next"

export const APP_ERROR_EVENT = "app:error"

export type ErrorBoundaryFallbackRender = (args: {
  error: Error | null
  resetError: () => void
}) => ReactNode

export type ErrorBoundaryProps = {
  children: ReactNode
  fallback?: ReactNode | ErrorBoundaryFallbackRender
  onReset?: () => void
}

type ErrorBoundaryState = {
  hasError: boolean
  error: Error | null
}

function DefaultFallback({ onRetry }: { onRetry: () => void }) {
  const { t } = useTranslation(["system"])
  return (
    <div
      role="alert"
      style={{
        minHeight: "100dvh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "1.5rem",
        padding: "2rem",
        textAlign: "center",
        backgroundColor: "var(--page-bg, #0b0d11)",
        color: "var(--page-text, #f5f7fa)",
      }}
    >
      <div style={{ maxWidth: "32rem" }}>
        <h1 style={{ fontSize: "clamp(1.5rem, 4vw, 2.5rem)", marginBottom: "0.5rem" }}>
          {t("system:errorBoundary.title")}
        </h1>
        <p style={{ opacity: 0.8, lineHeight: 1.6 }}>{t("system:errorBoundary.description")}</p>
      </div>
      <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", justifyContent: "center" }}>
        <button
          type="button"
          onClick={() => {
            if (typeof window !== "undefined" && typeof window.location?.reload === "function") {
              window.location.reload()
              return
            }
            onRetry()
          }}
          style={{
            padding: "0.75rem 1.5rem",
            fontSize: "1rem",
            borderRadius: "9999px",
            border: "none",
            cursor: "pointer",
            background: "#0b63f4",
            color: "white",
            fontWeight: 600,
          }}
        >
          {t("system:errorBoundary.reload")}
        </button>
        <button
          type="button"
          onClick={onRetry}
          style={{
            padding: "0.75rem 1.5rem",
            fontSize: "1rem",
            borderRadius: "9999px",
            border: "1px solid rgba(255, 255, 255, 0.4)",
            background: "transparent",
            color: "currentColor",
            cursor: "pointer",
            fontWeight: 500,
          }}
        >
          {t("system:errorBoundary.retry")}
        </button>
      </div>
    </div>
  )
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("[ErrorBoundary] Unhandled error captured", error, errorInfo)

    if (typeof window !== "undefined" && typeof window.dispatchEvent === "function") {
      const detail = { error, errorInfo }
      window.dispatchEvent(new CustomEvent(APP_ERROR_EVENT, { detail }))
    }
  }

  private reset = () => {
    this.setState({ hasError: false, error: null })
    this.props.onReset?.()
  }

  override render(): ReactNode {
    if (this.state.hasError) {
      const { fallback } = this.props
      if (typeof fallback === "function") {
        return fallback({ error: this.state.error, resetError: this.reset })
      }
      if (fallback) {
        return fallback
      }
      return <DefaultFallback onRetry={this.reset} />
    }

    return this.props.children
  }
}

export default ErrorBoundary
