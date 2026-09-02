import { afterEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import App from "../App"

vi.mock("@tanstack/react-start/client", () => ({
  StartClient: () => <div data-testid="start-client">hydrated router</div>,
}))

describe("App", () => {
  afterEach(() => {
    ;(
      window as typeof window & { __APP_BOOTSTRAP_FORCE_ERROR__?: boolean }
    ).__APP_BOOTSTRAP_FORCE_ERROR__ = false
  })

  it("mounts TanStack Start's hydration entry point", () => {
    render(<App />)

    expect(screen.getByTestId("start-client")).toHaveTextContent("hydrated router")
  })

  it("preserves the explicit bootstrap failure gate used by end-to-end tests", () => {
    ;(
      window as typeof window & { __APP_BOOTSTRAP_FORCE_ERROR__?: boolean }
    ).__APP_BOOTSTRAP_FORCE_ERROR__ = true

    expect(() => render(<App />)).toThrow("Bootstrap failed")
  })

  it("keeps the client entry safe to evaluate during SSR without window", () => {
    vi.stubGlobal("window", undefined)

    try {
      expect(() => App()).not.toThrow()
    } finally {
      vi.unstubAllGlobals()
    }
  })
})
