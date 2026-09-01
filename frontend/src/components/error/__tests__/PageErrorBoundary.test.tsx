import { render, screen, fireEvent } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"

const {
  routeState,
  navigateMock,
  translationState,
  captureExceptionMock,
  logErrorMock,
  useTranslationMock,
} = vi.hoisted(() => ({
  routeState: { current: "/start" },
  navigateMock: vi.fn(),
  translationState: { ready: true },
  captureExceptionMock: vi.fn(),
  logErrorMock: vi.fn(),
  useTranslationMock: vi.fn((..._namespaces: unknown[]) => ({
    t: (key: string, fallback?: string) => fallback ?? key,
    ready: translationState.ready,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  })),
}))

vi.mock("react-i18next", () => ({
  useTranslation: useTranslationMock,
}))
vi.mock("@tanstack/react-router", () => ({
  useRouterState: (opts?: { select?: (s: unknown) => unknown }) =>
    opts?.select ? opts.select({ location: { pathname: routeState.current } }) : routeState.current,
  useNavigate: () => navigateMock,
}))
vi.mock("@sentry/react", () => ({ captureException: captureExceptionMock }))
vi.mock("@/app/logger", () => ({ logError: logErrorMock, logDebug: vi.fn() }))

import * as Sentry from "@sentry/react"
import { PageErrorBoundary } from "@/components/error/PageErrorBoundary"

function Boom(): never {
  throw new Error("kaboom")
}

describe("PageErrorBoundary", () => {
  beforeEach(() => {
    routeState.current = "/start"
    translationState.ready = true
    vi.clearAllMocks()
    // React logs caught errors via console.error — silence to keep output clean.
    vi.spyOn(console, "error").mockImplementation(() => {})
  })
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.restoreAllMocks()
  })

  it("renders children when there is no error", () => {
    render(
      <PageErrorBoundary>
        <div>safe content</div>
      </PageErrorBoundary>
    )
    expect(screen.getByText("safe content")).toBeInTheDocument()
  })

  it("renders the fallback alert + reports to Sentry when a child throws", () => {
    render(
      <PageErrorBoundary pageName="events">
        <Boom />
      </PageErrorBoundary>
    )
    expect(screen.getByRole("alert")).toBeInTheDocument()
    expect(screen.getByText("Page Error")).toBeInTheDocument()
    expect(screen.getByText("Something went wrong loading this page.")).toBeInTheDocument()
    expect(useTranslationMock).toHaveBeenCalledWith(["system"])
    // DEV error details branch (import.meta.env.DEV is true under vitest)
    expect(screen.getByText("Non-API Error")).toBeInTheDocument()
    expect(Sentry.captureException).toHaveBeenCalledWith(
      expect.any(Error),
      expect.objectContaining({
        contexts: expect.objectContaining({
          react: expect.objectContaining({ componentStack: expect.any(String) }),
          page: { name: "events" },
        }),
        tags: { errorBoundary: "page", page: "events" },
      })
    )
    expect(logErrorMock).toHaveBeenCalledWith(
      "[PageErrorBoundary]",
      expect.objectContaining({ page: "events" })
    )
  })

  it("renders a custom fallback when provided", () => {
    render(
      <PageErrorBoundary fallback={<div>custom fallback</div>}>
        <Boom />
      </PageErrorBoundary>
    )
    expect(screen.getByText("custom fallback")).toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("shows the loading fallback while translations are not ready", () => {
    translationState.ready = false
    render(
      <PageErrorBoundary>
        <Boom />
      </PageErrorBoundary>
    )

    expect(screen.getByText("common:statuses.loading")).toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("renders structured API error details in development", () => {
    const apiError = Object.assign(new Error("validation failed"), {
      isAxiosError: true,
      response: {
        status: 422,
        data: {
          detail: [
            { type: "value_error", msg: "Title is required", loc: ["body", "title"] },
            { type: "value_error", msg: "General failure", loc: [] },
          ],
          trace_id: "trace-123",
        },
      },
    })
    function ApiBoom(): never {
      throw apiError
    }

    render(
      <PageErrorBoundary pageName="news">
        <ApiBoom />
      </PageErrorBoundary>
    )

    expect(screen.getByText("Status: 422")).toBeInTheDocument()
    expect(screen.getByText("Trace ID: trace-123")).toBeInTheDocument()
    expect(screen.getByText(/Title is required/)).toBeInTheDocument()
    expect(screen.getByText(/General failure/)).toBeInTheDocument()
  })

  it("falls back to the message when an error has no stack", () => {
    const error = new Error("message-only failure")
    error.stack = ""
    function MessageOnlyBoom(): never {
      throw error
    }

    const { container } = render(
      <PageErrorBoundary>
        <MessageOnlyBoom />
      </PageErrorBoundary>
    )

    expect(container.querySelector("pre")).toHaveTextContent("message-only failure")
  })

  it("navigates home from the fallback", () => {
    render(
      <PageErrorBoundary>
        <Boom />
      </PageErrorBoundary>
    )
    fireEvent.click(screen.getByText("Go Home"))
    expect(navigateMock).toHaveBeenCalledWith({ to: "/" })
  })

  it("retry re-renders children (which throw again → fallback persists)", () => {
    render(
      <PageErrorBoundary>
        <Boom />
      </PageErrorBoundary>
    )
    fireEvent.click(screen.getByText("Try Again"))
    expect(screen.getByRole("alert")).toBeInTheDocument()
  })

  it("resets on route change", () => {
    const { rerender } = render(
      <PageErrorBoundary>
        <Boom />
      </PageErrorBoundary>
    )
    expect(screen.getByRole("alert")).toBeInTheDocument()
    routeState.current = "/other"
    rerender(
      <PageErrorBoundary>
        <div>recovered view</div>
      </PageErrorBoundary>
    )
    expect(screen.getByText("recovered view")).toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("reports an error without development logging in production", () => {
    vi.stubEnv("DEV", false)

    render(
      <PageErrorBoundary pageName="production-page">
        <Boom />
      </PageErrorBoundary>
    )

    expect(screen.getByRole("alert")).toBeInTheDocument()
    expect(Sentry.captureException).toHaveBeenCalled()
    expect(logErrorMock).not.toHaveBeenCalled()
  })

  it("omits an empty API details list from the development diagnostics", () => {
    const apiError = Object.assign(new Error("no field details"), {
      isAxiosError: true,
      response: {
        status: 422,
        data: { detail: [], trace_id: "trace-empty" },
      },
    })
    function EmptyDetailsBoom(): never {
      throw apiError
    }

    const { container } = render(
      <PageErrorBoundary>
        <EmptyDetailsBoom />
      </PageErrorBoundary>
    )

    expect(screen.getByText("Status: 422")).toBeInTheDocument()
    expect(container.querySelector("ul")).not.toBeInTheDocument()
  })

  it("labels detail entries without a field as Error", () => {
    const apiError = Object.assign(new Error("detail failure"), {
      isAxiosError: true,
      response: {
        status: 422,
        data: {
          detail: [{ type: "value_error", msg: "General failure", loc: [] }],
        },
      },
    })
    function UnfieldedBoom(): never {
      throw apiError
    }

    render(
      <PageErrorBoundary>
        <UnfieldedBoom />
      </PageErrorBoundary>
    )

    expect(screen.getByRole("listitem")).toHaveTextContent("Error: General failure")
  })
})
