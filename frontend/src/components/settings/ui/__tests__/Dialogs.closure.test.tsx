import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("@/hooks/useFocusTrap", () => ({ default: () => ({ current: null }) }))

import { Dialog, DialogActions, DialogContent, DialogTitle } from "@/components/settings/ui/Dialogs"

describe("settings Dialog closure paths", () => {
  it("falls back to the default width and renders optional labelled content", () => {
    const onClose = vi.fn()
    render(
      <Dialog open onClose={onClose} maxWidth="unsupported" ariaLabelledBy="dialog-title">
        <DialogTitle id="dialog-title">Title</DialogTitle>
        <DialogContent id="dialog-content">Body</DialogContent>
        <DialogActions>Actions</DialogActions>
      </Dialog>
    )

    const dialog = screen.getByRole("dialog", { name: "Title" })
    expect(dialog).toHaveClass("max-w-[28rem]")
    expect(dialog).toHaveAttribute("aria-labelledby", "dialog-title")
    expect(screen.getByText("Body")).toBeInTheDocument()

    const backdrop = screen.getByRole("presentation").firstElementChild
    expect(backdrop).not.toBeNull()
    fireEvent.click(backdrop!)
    expect(onClose).toHaveBeenCalledOnce()
  })

  it("uses the full-width branch when requested", () => {
    render(
      <Dialog open onClose={vi.fn()} maxWidth="xs" fullWidth>
        <DialogContent>Wide</DialogContent>
      </Dialog>
    )
    expect(screen.getByRole("dialog")).toHaveClass("w-full")
  })
})
