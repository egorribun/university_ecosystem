import { render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

vi.mock("react-i18next", () => ({
  withTranslation: () => (Component: React.ComponentType<Record<string, unknown>>) => {
    function WithTranslationMock(props: Record<string, unknown>) {
      return <Component {...props} t={(key: string) => key} />
    }

    return WithTranslationMock
  },
}))
vi.mock("@sentry/react", () => ({ captureException: vi.fn() }))
vi.mock("@/app/logger", () => ({ logError: vi.fn() }))

import ErrorBoundary from "@/components/feedback/ErrorBoundary"
import { logError } from "@/app/logger"

function BrokenChild(): never {
  throw new Error("production failure")
}

describe("feedback ErrorBoundary production behavior", () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.restoreAllMocks()
  })

  it("renders its safe fallback without development-only logging", () => {
    vi.stubEnv("DEV", false)
    vi.spyOn(console, "error").mockImplementation(() => undefined)

    render(
      <ErrorBoundary>
        <BrokenChild />
      </ErrorBoundary>
    )

    expect(screen.getByText("system:errorBoundary.title")).toBeInTheDocument()
    expect(screen.queryByText("system:errorBoundary.details")).not.toBeInTheDocument()
    expect(logError).not.toHaveBeenCalled()
  })
})
