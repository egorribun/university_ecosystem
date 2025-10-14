import { type JSX, useState } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import ErrorBoundary, { APP_ERROR_EVENT } from "./ErrorBoundary"
import i18n from "@/i18n/config"

describe("ErrorBoundary", () => {
  it("logs, dispatches and renders a fallback screen", () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {})
    const dispatchSpy = vi.spyOn(window, "dispatchEvent")

    const Problem = (): JSX.Element => {
      throw new Error("Boom")
    }

    render(
      <ErrorBoundary>
        <Problem />
      </ErrorBoundary>
    )

    expect(
      consoleSpy.mock.calls.some((call) => call[0] === "[ErrorBoundary] Unhandled error captured")
    ).toBe(true)

    const eventCall = dispatchSpy.mock.calls.find((call) => call[0] instanceof CustomEvent)
    expect(eventCall?.[0]).toBeInstanceOf(CustomEvent)
    expect((eventCall?.[0] as CustomEvent<unknown>).type).toBe(APP_ERROR_EVENT)

    expect(
      screen.getByRole("heading", { name: i18n.t("system:errorBoundary.title") }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: i18n.t("system:errorBoundary.reload") }),
    ).toBeInTheDocument()

    consoleSpy.mockRestore()
    dispatchSpy.mockRestore()
  })

  it("allows retrying rendering after the issue is resolved", async () => {
    const user = userEvent.setup()

    function Harness() {
      const [shouldThrow, setShouldThrow] = useState(true)

      return (
        <ErrorBoundary
          fallback={({ resetError }) => (
            <div>
              <span>fallback</span>
              <button
                type="button"
                onClick={() => {
                  setShouldThrow(false)
                  resetError()
                }}
              >
                retry
              </button>
            </div>
          )}
        >
          {shouldThrow ? <Problem /> : <p>recovered</p>}
        </ErrorBoundary>
      )
    }

    function Problem(): JSX.Element {
      throw new Error("Controlled failure")
    }

    render(<Harness />)

    expect(screen.getByText("fallback")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "retry" }))
    expect(screen.getByText("recovered")).toBeInTheDocument()
  })
})
