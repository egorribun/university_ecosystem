/**
 * Tests for error boundary components
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"

const mocks = vi.hoisted(() => ({
  captureException: vi.fn(),
  logError: vi.fn(),
  logWarning: vi.fn(),
}))
const translationMock = vi.hoisted(() => {
  const t = vi.fn((key: string, options?: { feature?: string }) => {
    if (key === "common:errors.featureUnavailable") {
      return `${options?.feature ?? "Feature"} unavailable`
    }
    if (key === "common:statuses.error") return "Something went wrong"
    if (key === "common:statuses.tryAgain") return "Try again"
    return key
  })
  return {
    t,
    useTranslation: vi.fn((..._namespaces: unknown[]) => ({
      t,
      i18n: { language: "en", changeLanguage: () => Promise.resolve() },
    })),
  }
})

vi.mock("react-i18next", () => ({
  useTranslation: translationMock.useTranslation,
}))

import { FeatureErrorBoundary } from "../FeatureErrorBoundary"
import { WidgetErrorBoundary } from "../WidgetErrorBoundary"

// Mock Sentry
vi.mock("@sentry/react", () => ({
  captureException: mocks.captureException,
}))
vi.mock("@/app/logger", () => ({
  logError: mocks.logError,
  logWarning: mocks.logWarning,
}))

import * as Sentry from "@sentry/react"

// Suppress console errors during tests
let consoleError: ReturnType<typeof vi.spyOn>
let consoleWarn: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  consoleError = vi.spyOn(console, "error").mockImplementation(() => {})
  consoleWarn = vi.spyOn(console, "warn").mockImplementation(() => {})
  vi.clearAllMocks()
})

afterEach(() => {
  vi.unstubAllEnvs()
  consoleError.mockRestore()
  consoleWarn.mockRestore()
})

// Component that throws
function BrokenComponent({ shouldThrow = true }: { shouldThrow?: boolean }) {
  if (shouldThrow) {
    throw new Error("Test error")
  }
  return <div>Working component</div>
}

describe("FeatureErrorBoundary", () => {
  it("renders children when no error", () => {
    render(
      <FeatureErrorBoundary>
        <BrokenComponent shouldThrow={false} />
      </FeatureErrorBoundary>
    )

    expect(screen.getByText("Working component")).toBeInTheDocument()
  })

  it("renders default fallback on error", () => {
    render(
      <FeatureErrorBoundary featureName="Schedule">
        <BrokenComponent />
      </FeatureErrorBoundary>
    )

    expect(screen.getByText("Schedule unavailable")).toBeInTheDocument()
    expect(screen.getByText("Try again")).toBeInTheDocument()
    expect(translationMock.useTranslation).toHaveBeenCalledWith(["common"])
    expect(screen.getByText("Something went wrong")).toHaveClass("text-xs")
    expect(screen.getByText("Try again")).toHaveClass("text-xs", "font-black")
    expect(Sentry.captureException).toHaveBeenCalledWith(
      expect.any(Error),
      expect.objectContaining({
        contexts: expect.objectContaining({
          react: expect.objectContaining({ componentStack: expect.any(String) }),
          feature: { name: "Schedule" },
        }),
        tags: { errorBoundary: "feature", feature: "Schedule" },
        level: "warning",
      })
    )
    expect(mocks.logError).toHaveBeenCalledWith(
      "[FeatureErrorBoundary]",
      expect.objectContaining({ feature: "Schedule" })
    )
  })

  it("renders custom fallback on error", () => {
    render(
      <FeatureErrorBoundary fallback={<div>Custom error</div>}>
        <BrokenComponent />
      </FeatureErrorBoundary>
    )

    expect(screen.getByText("Custom error")).toBeInTheDocument()
  })

  it("resets state on retry click", async () => {
    const user = userEvent.setup()
    render(
      <FeatureErrorBoundary featureName="Test">
        <BrokenComponent shouldThrow={true} />
      </FeatureErrorBoundary>
    )

    // Error state shown
    expect(screen.getByText("Test unavailable")).toBeInTheDocument()
    expect(screen.getByRole("alert")).toBeInTheDocument()

    // Retry button is present and clickable
    const retryButton = screen.getByText("Try again")
    expect(retryButton).toBeInTheDocument()

    // Click triggers reset (even though component will error again)
    await user.click(retryButton)
    // The boundary attempts to render children, which throws again
    // This verifies the reset mechanism works
    expect(screen.getByText("Test unavailable")).toBeInTheDocument()
  })

  it("calls onError callback", () => {
    const onError = vi.fn()

    render(
      <FeatureErrorBoundary onError={onError}>
        <BrokenComponent />
      </FeatureErrorBoundary>
    )

    expect(onError).toHaveBeenCalledTimes(1)
    expect(onError.mock.calls[0]![0]).toBeInstanceOf(Error)
  })

  it("can suppress Sentry reporting and development logging", () => {
    vi.stubEnv("DEV", false)

    render(
      <FeatureErrorBoundary reportToSentry={false}>
        <BrokenComponent />
      </FeatureErrorBoundary>
    )

    expect(screen.getByRole("alert")).toBeInTheDocument()
    expect(Sentry.captureException).not.toHaveBeenCalled()
    expect(mocks.logError).not.toHaveBeenCalled()
  })

  it("successfully recovers when retrying after a transient child error", async () => {
    const user = userEvent.setup()
    let shouldThrow = true
    function FlakyComponent() {
      if (shouldThrow) throw new Error("transient")
      return <div>Recovered feature</div>
    }

    render(
      <FeatureErrorBoundary featureName="Transient feature">
        <FlakyComponent />
      </FeatureErrorBoundary>
    )
    expect(screen.getByText("Transient feature unavailable")).toBeInTheDocument()

    shouldThrow = false
    await user.click(screen.getByText("Try again"))
    expect(screen.getByText("Recovered feature")).toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })
})

describe("WidgetErrorBoundary", () => {
  it("renders children when no error", () => {
    render(
      <WidgetErrorBoundary>
        <BrokenComponent shouldThrow={false} />
      </WidgetErrorBoundary>
    )

    expect(screen.getByText("Working component")).toBeInTheDocument()
  })

  it("renders nothing by default on error (silent failure)", () => {
    const { container } = render(
      <WidgetErrorBoundary widgetName="Weather">
        <BrokenComponent />
      </WidgetErrorBoundary>
    )

    // Should be empty
    expect(container.firstChild).toBeNull()
  })

  it("renders placeholder when showFallback is true", () => {
    render(
      <WidgetErrorBoundary showFallback>
        <BrokenComponent />
      </WidgetErrorBoundary>
    )

    // Should render placeholder with dash
    expect(screen.getByText("—")).toBeInTheDocument()
  })

  it("renders custom fallback on error", () => {
    render(
      <WidgetErrorBoundary fallback={<div>Widget failed</div>}>
        <BrokenComponent />
      </WidgetErrorBoundary>
    )

    expect(screen.getByText("Widget failed")).toBeInTheDocument()
  })

  it("calls onError callback", () => {
    const onError = vi.fn()

    render(
      <WidgetErrorBoundary onError={onError}>
        <BrokenComponent />
      </WidgetErrorBoundary>
    )

    expect(onError).toHaveBeenCalledTimes(1)
    expect(onError.mock.calls[0]![0]).toBeInstanceOf(Error)
    expect(Sentry.captureException).toHaveBeenCalledWith(
      expect.any(Error),
      expect.objectContaining({
        contexts: expect.objectContaining({
          react: expect.objectContaining({ componentStack: expect.any(String) }),
          widget: { name: undefined },
        }),
        tags: { errorBoundary: "widget", widget: undefined },
        level: "info",
      })
    )
  })

  it("keeps the silent fallback in production without development logging", () => {
    vi.stubEnv("DEV", false)

    const { container } = render(
      <WidgetErrorBoundary>
        <BrokenComponent />
      </WidgetErrorBoundary>
    )

    expect(container.firstChild).toBeNull()
    expect(mocks.logWarning).not.toHaveBeenCalled()
  })

  it("honours an explicit showFallback=false value", () => {
    const { container } = render(
      <WidgetErrorBoundary showFallback={false}>
        <BrokenComponent />
      </WidgetErrorBoundary>
    )

    expect(container.firstChild).toBeNull()
  })
})
