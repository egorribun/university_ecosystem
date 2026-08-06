import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"
import { useRef, useState } from "react"
import useFocusTrap from "../useFocusTrap"

describe("useFocusTrap", () => {
  afterEach(() => {
    document.body.innerHTML = ""
    vi.restoreAllMocks()
  })

  it("focuses the initial element and restores focus on close", async () => {
    const user = userEvent.setup()

    const Trigger = () => {
      const [open, setOpen] = useState(false)
      const closeRef = useRef<HTMLButtonElement | null>(null)
      const containerRef = useFocusTrap<HTMLDivElement>({
        active: open,
        initialFocus: () => closeRef.current ?? document.body,
        fallbackFocus: () => closeRef.current ?? document.body,
        onDeactivate: () => setOpen(false),
      })

      return (
        <div>
          <button type="button" onClick={() => setOpen(true)}>
            Open drawer
          </button>
          {open && (
            <div ref={containerRef}>
              <button ref={closeRef} type="button">
                Close
              </button>
              <button type="button">Next</button>
            </div>
          )}
        </div>
      )
    }

    render(<Trigger />)

    const opener = screen.getByRole("button", { name: "Open drawer" })
    opener.focus()

    await user.click(opener)

    const closeButton = await screen.findByRole("button", { name: "Close" })
    const container = closeButton.parentElement
    expect(container).not.toBeNull()
    await waitFor(() => expect(container).toContainElement(document.activeElement as HTMLElement))

    await user.keyboard("{Escape}")

    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Close" })).not.toBeInTheDocument()
    )
    await waitFor(() => expect(opener).toHaveFocus())
  })

  it("invokes onDeactivate when trap deactivates", async () => {
    const user = userEvent.setup()
    const onDeactivate = vi.fn()

    const Wrapper = () => {
      const [active, setActive] = useState(true)
      const closeRef = useRef<HTMLButtonElement | null>(null)
      const containerRef = useFocusTrap<HTMLDivElement>({
        active,
        initialFocus: () => closeRef.current ?? document.body,
        onDeactivate: () => {
          onDeactivate()
          setActive(false)
        },
      })

      return (
        <div>
          {active && (
            <div ref={containerRef} tabIndex={-1}>
              <button ref={closeRef} type="button">
                Close trap
              </button>
            </div>
          )}
        </div>
      )
    }

    render(<Wrapper />)

    await user.keyboard("{Escape}")

    expect(onDeactivate).toHaveBeenCalledTimes(1)
  })
})
