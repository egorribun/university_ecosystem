import { render, screen, fireEvent } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"

const { routeState, navigateMock, translationState } = vi.hoisted(() => ({
  routeState: { current: "/start" },
  navigateMock: vi.fn(),
  translationState: { ready: true },
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    ready: translationState.ready,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))
vi.mock("@tanstack/react-router", () => ({
  useRouterState: (opts?: { select?: (s: unknown) => unknown }) =>
    opts?.select ? opts.select({ location: { pathname: routeState.current } }) : routeState.current,
  useNavigate: () => navigateMock,
}))
vi.mock("@sentry/react", () => ({ captureException: vi.fn() }))
vi.mock("@/app/logger", () => ({ logError: vi.fn(), logDebug: vi.fn() }))

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
    expect(screen.getByText("system:pageError.title")).toBeInTheDocument()
    // DEV error details branch (import.meta.env.DEV is true under vitest)
    expect(screen.getByText("Non-API Error")).toBeInTheDocument()
    expect(Sentry.captureException).toHaveBeenCalledWith(
      expect.any(Error),
      expect.objectContaining({ contexts: expect.objectContaining({ page: { name: "events" } }) })
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
    fireEvent.click(screen.getByText("system:pageError.home"))
    expect(navigateMock).toHaveBeenCalledWith({ to: "/" })
  })

  it("retry re-renders children (which throw again → fallback persists)", () => {
    render(
      <PageErrorBoundary>
        <Boom />
      </PageErrorBoundary>
    )
    fireEvent.click(screen.getByText("system:pageError.retry"))
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
  })
})
