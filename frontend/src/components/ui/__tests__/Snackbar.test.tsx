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

  it("does not schedule an auto-close while closed or without a message", () => {
    vi.useFakeTimers()
    const onClose = vi.fn()
    const { rerender } = render(<Snackbar open={false} message="Hidden" onClose={onClose} />)
    vi.advanceTimersByTime(5000)
    rerender(<Snackbar open message="" onClose={onClose} />)
    vi.advanceTimersByTime(5000)

    expect(onClose).not.toHaveBeenCalled()
  })

  it("restarts the auto-close window when a new message replaces the old one", () => {
    vi.useFakeTimers()
    const onClose = vi.fn()
    const { rerender } = render(<Snackbar open message="First" onClose={onClose} duration={1000} />)
    vi.advanceTimersByTime(600)
    rerender(<Snackbar open message="Second" onClose={onClose} duration={1000} />)
    vi.advanceTimersByTime(600)

    expect(onClose).not.toHaveBeenCalled()
    vi.advanceTimersByTime(400)
    expect(onClose).toHaveBeenCalledOnce()
  })

  it("cancels the pending auto-close when dismissed early", () => {
    vi.useFakeTimers()
    const onClose = vi.fn()
    const { rerender } = render(<Snackbar open message="Bye" onClose={onClose} duration={1000} />)
    rerender(<Snackbar open={false} message="Bye" onClose={onClose} duration={1000} />)
    vi.advanceTimersByTime(2000)

    expect(onClose).not.toHaveBeenCalled()
  })
})
