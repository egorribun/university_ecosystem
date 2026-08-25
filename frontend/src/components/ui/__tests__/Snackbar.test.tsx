import { afterEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"

import Snackbar from "@/components/ui/Snackbar"

// Pure component (no providers); fake timers exercise the auto-close branch.

describe("Snackbar", () => {
  afterEach(() => vi.useRealTimers())

  it("renders the message when open", () => {
    render(<Snackbar open message="Saved!" onClose={() => {}} />)
    const status = screen.getByRole("status")
    expect(status).toHaveTextContent("Saved!")
    expect(status).toHaveAttribute("aria-live", "polite")
    expect(status).toHaveAttribute("aria-atomic", "true")
  })

  it("renders nothing when closed", () => {
    const { container } = render(<Snackbar open={false} message="Hidden" onClose={() => {}} />)
    expect(container.firstChild).toBeNull()
  })

  it("renders nothing when the message is empty", () => {
    const { container } = render(<Snackbar open message="" onClose={() => {}} />)
    expect(container.firstChild).toBeNull()
  })

  it("auto-closes after the duration elapses", () => {
    vi.useFakeTimers()
    const onClose = vi.fn()
    render(<Snackbar open message="Bye" onClose={onClose} duration={1000} />)
    expect(onClose).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1000)
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
