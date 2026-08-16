import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { ErrorBoundary } from "./ErrorBoundary"
import * as Sentry from "@sentry/react"
// i18n mocked below

// Mock Sentry
vi.mock("@sentry/react", () => ({
  captureException: vi.fn(),
}))

// Mock i18next
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { changeLanguage: vi.fn(), language: "en" },
  }),
  withTranslation: () => (Component: React.ComponentType<Record<string, unknown>>) => {
    // Inject mock 't' function into props
    const TranslatedComponent = (props: Record<string, unknown>) => (
      <Component {...props} t={(key: string) => key} />
    )
    return TranslatedComponent
  },
  initReactI18next: { type: "3rdParty", init: vi.fn() },
}))

// Mock i18next core for good measure
vi.mock("i18next", () => ({
  default: {
    t: (key: string) => key,
    changeLanguage: vi.fn(),
  },
}))

describe("ErrorBoundary", () => {
  const originalEnv = process.env.NODE_ENV

  beforeEach(() => {
    vi.clearAllMocks()
    // Suppress console.error during tests to avoid noise from expected errors
    vi.spyOn(console, "error").mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
    process.env.NODE_ENV = originalEnv
  })

  const ThrowError = ({ message = "Test Error" }: { message?: string }) => {
    throw new Error(message)
  }

  it("renders children when no error occurs", () => {
    render(
      <ErrorBoundary>
        <div>Content</div>
      </ErrorBoundary>
    )
    expect(screen.getByText("Content")).toBeInTheDocument()
  })

  it("renders default fallback UI when an error occurs", () => {
    render(
      <ErrorBoundary>
        <ThrowError />
      </ErrorBoundary>
    )

    expect(screen.getByText("system:errorBoundary.title")).toBeInTheDocument()
    expect(screen.getByText("system:errorBoundary.description")).toBeInTheDocument()
    expect(Sentry.captureException).toHaveBeenCalled()
  })

  it("calls onError prop when an error occurs", () => {
    const onError = vi.fn()
    render(
      <ErrorBoundary onError={onError}>
        <ThrowError />
      </ErrorBoundary>
    )
    expect(onError).toHaveBeenCalled()
  })

  it("renders custom fallback if provided", () => {
    render(
      <ErrorBoundary fallback={<div>Custom Fallback</div>}>
        <ThrowError />
      </ErrorBoundary>
    )
    expect(screen.getByText("Custom Fallback")).toBeInTheDocument()
    expect(screen.queryByText("system:errorBoundary.title")).not.toBeInTheDocument()
  })

  it("resets state when retry button is clicked", async () => {
    // TestComponent removed as it was unused

    // We need a parent component to handle the reset/unmount logic effectively in a real integration test,
    // but for unit testing the boundary's handleRetry:

    // Using a slightly different approach:
    // The ErrorBoundary's handleRetry sets hasError: false.
    // This will cause a re-render of children.
    // If children still throw, it will catch again.

    // Let's just verify the button exists and is clickable.
    const user = userEvent.setup()
    render(
      <ErrorBoundary>
        <ThrowError />
      </ErrorBoundary>
    )

    const retryBtn = screen.getByText("system:errorBoundary.retry")
    expect(retryBtn).toBeInTheDocument()
    await user.click(retryBtn)

    // After click, it attempts to render children again.
    // Since ThrowError throws immediately, it will catch again and likely cycle or stay in error state.
    // But we just wanted to basic check.
    expect(Sentry.captureException).toHaveBeenCalledTimes(2) // Once initial, once after retry
  })

  it("offers reload and home recovery actions", async () => {
    const user = userEvent.setup()
    render(
      <ErrorBoundary>
        <ThrowError />
      </ErrorBoundary>
    )

    await user.click(screen.getByText("system:errorBoundary.reload"))
    await user.click(screen.getByText("system:errorBoundary.goHome"))

    expect(screen.getByText("system:errorBoundary.title")).toBeInTheDocument()
  })
})
