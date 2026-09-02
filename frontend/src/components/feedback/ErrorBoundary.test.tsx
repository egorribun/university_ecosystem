import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import {
  createErrorBoundaryInitialState,
  ERROR_BOUNDARY_DETAIL_BACKGROUND,
  ERROR_BOUNDARY_RADIAL_BACKGROUND,
  ErrorBoundary,
  ErrorBoundaryInner,
} from "./ErrorBoundary"
import * as Sentry from "@sentry/react"
import { logError } from "@/app/logger"
// i18n mocked below

// Mock Sentry
vi.mock("@sentry/react", () => ({
  captureException: vi.fn(),
}))

vi.mock("@/app/logger", () => ({
  logError: vi.fn(),
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
    expect(createErrorBoundaryInitialState()).toStrictEqual({
      hasError: false,
      error: null,
      errorInfo: null,
    })
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
    expect(screen.getByText("system:errorBoundary.details")).toBeInTheDocument()
    expect(screen.getByText("Error: Test Error")).toBeInTheDocument()
    const details = screen.getByText("system:errorBoundary.details").closest("details")
    expect(details).not.toBeNull()
    const detailPre = details?.querySelectorAll("pre")
    expect(detailPre).toHaveLength(2)
    expect(detailPre?.[0]?.getAttribute("style")).toContain(
      `background-color: ${ERROR_BOUNDARY_DETAIL_BACKGROUND}`
    )
    expect(detailPre?.[1]?.getAttribute("style")).toContain(
      `background-color: ${ERROR_BOUNDARY_DETAIL_BACKGROUND}`
    )
    const glow = document.querySelector<HTMLElement>(".pointer-events-none.absolute.inset-0")
    expect(glow?.getAttribute("style")).toContain(
      `background-image: ${ERROR_BOUNDARY_RADIAL_BACKGROUND}`
    )
    expect(logError).toHaveBeenCalledWith(
      "ErrorBoundary caught an error:",
      expect.objectContaining({
        error: expect.any(Error),
        errorInfo: expect.objectContaining({ componentStack: expect.any(String) }),
      })
    )
    expect(screen.getAllByRole("button").map((button) => button.textContent)).toEqual([
      "system:errorBoundary.retry",
      "system:errorBoundary.reload",
      "system:errorBoundary.goHome",
    ])
    expect(Sentry.captureException).toHaveBeenCalled()
    expect(Sentry.captureException).toHaveBeenCalledWith(
      expect.any(Error),
      expect.objectContaining({
        contexts: expect.objectContaining({
          react: expect.objectContaining({ componentStack: expect.any(String) }),
        }),
      })
    )
  })

  it("preserves a recoverable boundary state when retrying", async () => {
    const user = userEvent.setup()
    let shouldThrow = true
    function RecoverableChild() {
      if (shouldThrow) throw new Error("recoverable")
      return <div>Recovered content</div>
    }

    const { rerender } = render(
      <ErrorBoundary>
        <RecoverableChild />
      </ErrorBoundary>
    )
    shouldThrow = false
    await user.click(screen.getByText("system:errorBoundary.retry"))
    rerender(
      <ErrorBoundary>
        <RecoverableChild />
      </ErrorBoundary>
    )

    expect(screen.getByText("Recovered content")).toBeInTheDocument()
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
    const originalLocation = Object.getOwnPropertyDescriptor(window, "location")
    const reload = vi.fn()
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { href: "/before-error", reload },
    })

    try {
      render(
        <ErrorBoundary>
          <ThrowError />
        </ErrorBoundary>
      )

      await user.click(screen.getByText("system:errorBoundary.reload"))
      await user.click(screen.getByText("system:errorBoundary.goHome"))

      expect(reload).toHaveBeenCalledOnce()
      expect(window.location.href).toBe("/")
      expect(screen.getByText("system:errorBoundary.title")).toBeInTheDocument()
    } finally {
      if (originalLocation) Object.defineProperty(window, "location", originalLocation)
    }
  })

  it("does not render development details when the captured error is absent", () => {
    const instance = new ErrorBoundaryInner({ children: null, t: (key: string) => key } as never)
    instance.state = { hasError: true, error: null, errorInfo: null }

    const { container } = render(instance.render())

    expect(container.querySelector("details")).not.toBeInTheDocument()
  })

  it("does not render a component stack when error metadata is absent", () => {
    const instance = new ErrorBoundaryInner({ children: null, t: (key: string) => key } as never)
    instance.state = { hasError: true, error: new Error("without metadata"), errorInfo: null }

    const { container } = render(instance.render())

    expect(container.querySelectorAll("details pre")).toHaveLength(1)
  })
})
