import { createRef } from "react"
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
  routeState: {
    current: "/start",
    selectors: [] as Array<((state: unknown) => unknown) | undefined>,
  },
  navigateMock: vi.fn(),
  translationState: { ready: true },
  captureExceptionMock: vi.fn(),
  logErrorMock: vi.fn(),
  useTranslationMock: vi.fn((..._namespaces: unknown[]) => ({
    t: (key: string, fallback?: string) => {
      const catalog: Record<string, string> = {
        "system:pageError.title": "Page Error",
        "system:pageError.description": "Something went wrong loading this page.",
        "system:pageError.retry": "Try Again",
        "system:pageError.home": "Go Home",
      }
      return catalog[key] ?? fallback ?? key
    },
    ready: translationState.ready,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  })),
}))

vi.mock("react-i18next", () => ({
  useTranslation: useTranslationMock,
}))
vi.mock("@tanstack/react-router", () => ({
  useRouterState: (opts?: { select?: (s: unknown) => unknown }) => {
    routeState.selectors.push(opts?.select)
    return opts?.select
      ? opts.select({ location: { pathname: routeState.current } })
      : routeState.current
  },
  useNavigate: () => navigateMock,
}))
vi.mock("@sentry/react", () => ({ captureException: captureExceptionMock }))
vi.mock("@/app/logger", () => ({ logError: logErrorMock, logDebug: vi.fn() }))

import * as Sentry from "@sentry/react"
import {
  PageErrorBoundary,
  PageErrorBoundaryClass,
  PageErrorFallback,
} from "@/components/error/PageErrorBoundary"
import { ApiResponseValidationError } from "@/api/validation"

function Boom(): never {
  throw new Error("kaboom")
}

describe("PageErrorBoundary", () => {
  beforeEach(() => {
    routeState.current = "/start"
    routeState.selectors = []
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

  it("requests a pathname selector from the router state", () => {
    render(
      <PageErrorBoundary>
        <div>selected content</div>
      </PageErrorBoundary>
    )

    const selector = routeState.selectors[0]
    expect(selector).toEqual(expect.any(Function))
    expect(selector?.({ location: { pathname: "/selected" } })).toBe("/selected")
  })

  it("starts with a fully initialized class state", () => {
    const ref = createRef<PageErrorBoundaryClass>()
    render(
      <PageErrorBoundaryClass ref={ref} locationKey="/start" onNavigateHome={navigateMock}>
        <div>safe class content</div>
      </PageErrorBoundaryClass>
    )

    expect(ref.current?.state).toEqual({ hasError: false, error: null, errorInfo: null })
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

  it("records React error information on the class boundary", () => {
    const ref = createRef<PageErrorBoundaryClass>()
    render(
      <PageErrorBoundaryClass ref={ref} locationKey="/start" onNavigateHome={navigateMock}>
        <Boom />
      </PageErrorBoundaryClass>
    )

    expect(ref.current?.state.errorInfo?.componentStack).toEqual(expect.any(String))
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
    expect(screen.queryByText("Non-API Error")).not.toBeInTheDocument()
    expect(Sentry.captureException).toHaveBeenCalled()
    expect(logErrorMock).not.toHaveBeenCalled()
  })

  it("keeps the fallback diagnostics behind the development flag", () => {
    vi.stubEnv("DEV", false)

    render(
      <PageErrorFallback
        error={new Error("direct production error")}
        onRetry={vi.fn()}
        onGoHome={vi.fn()}
      />
    )

    expect(screen.getByRole("alert")).toBeInTheDocument()
    expect(screen.queryByText("Non-API Error")).not.toBeInTheDocument()
    expect(screen.queryByText("Error details")).not.toBeInTheDocument()
  })

  it("renders direct development diagnostics for non-API errors", () => {
    render(
      <PageErrorFallback
        error={new Error("direct diagnostic error")}
        onRetry={vi.fn()}
        onGoHome={vi.fn()}
      />
    )

    expect(screen.getByText("Non-API Error")).toBeInTheDocument()
    expect(screen.getByText("direct diagnostic error")).toBeInTheDocument()
  })

  it("always returns fallback UI from the fallback component", () => {
    const fallback = PageErrorFallback({
      error: new Error("direct component invocation"),
      onRetry: vi.fn(),
      onGoHome: vi.fn(),
    })

    expect(fallback).toBeTruthy()
  })

  it("renders a positive API status in direct development diagnostics", () => {
    const error = Object.assign(new Error("direct api error"), {
      isAxiosError: true,
      response: { status: 422, data: { detail: [] } },
    })

    render(<PageErrorFallback error={error} onRetry={vi.fn()} onGoHome={vi.fn()} />)

    expect(screen.getByText("Status: 422")).toBeInTheDocument()
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

  it("keeps an explicitly empty validation issue list out of diagnostics", () => {
    const error = new ApiResponseValidationError([])
    function EmptyValidationBoom(): never {
      throw error
    }

    const { container } = render(
      <PageErrorBoundary>
        <EmptyValidationBoom />
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
