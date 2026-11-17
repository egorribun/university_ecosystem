import { useState } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import useFocusTrap from "@/hooks/useFocusTrap"
import { ConfirmDialog } from "./ConfirmDialog"

// Keep the real focus-trap lifecycle and keyboard handling; jsdom has no layout.
vi.mock("focus-trap", async (importOriginal) => {
  const actual = await importOriginal<typeof import("focus-trap")>()
  return {
    ...actual,
    createFocusTrap: (
      container: Parameters<typeof actual.createFocusTrap>[0],
      options: Parameters<typeof actual.createFocusTrap>[1]
    ) =>
      actual.createFocusTrap(container, {
        ...options,
        tabbableOptions: { displayCheck: "none" },
      }),
  }
})

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)

function Harness({
  loading = false,
  onCancel = () => {},
  onConfirm = () => {},
}: {
  loading?: boolean
  onCancel?: () => void
  onConfirm?: () => void
}) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button onClick={() => setOpen(true)}>Open confirmation</button>
      <ConfirmDialog
        open={open}
        title="Delete item?"
        message="This cannot be undone."
        cancelText="Cancel"
        confirmText="Delete"
        isLoading={loading}
        onCancel={() => {
          onCancel()
          setOpen(false)
        }}
        onConfirm={onConfirm}
      />
      <button>Outside action</button>
    </>
  )
}

describe("ConfirmDialog focus lifecycle", () => {
  it("focuses Cancel, contains keyboard traversal and returns focus after Escape", async () => {
    const user = userEvent.setup()
    const onCancel = vi.fn()
    const onConfirm = vi.fn()
    render(<Harness onCancel={onCancel} onConfirm={onConfirm} />)
    const opener = screen.getByRole("button", { name: "Open confirmation" })
    await user.click(opener)
    const cancel = screen.getByRole("button", { name: "Cancel" })
    const confirm = screen.getByRole("button", { name: "Delete" })
    await waitFor(() => expect(cancel).toHaveFocus())

    await user.tab({ shift: true })
    expect(confirm).toHaveFocus()
    await user.tab()
    expect(cancel).toHaveFocus()
    await user.keyboard("{Escape}")

    expect(onCancel).toHaveBeenCalledOnce()
    expect(onConfirm).not.toHaveBeenCalled()
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument()
    await waitFor(() => expect(opener).toHaveFocus())
  })

  it("retains containment and blocks Escape while the confirmation is loading", async () => {
    const user = userEvent.setup()
    const onCancel = vi.fn()
    const onConfirm = vi.fn()
    const view = render(<Harness loading onCancel={onCancel} onConfirm={onConfirm} />)
    await user.click(screen.getByRole("button", { name: "Open confirmation" }))
    const dialog = screen.getByRole("alertdialog")
    await waitFor(() => expect(dialog).toHaveFocus())

    await user.tab()
    expect(dialog).toHaveFocus()
    await user.keyboard("{Escape}")
    expect(onCancel).not.toHaveBeenCalled()
    expect(onConfirm).not.toHaveBeenCalled()
    expect(dialog).toBeInTheDocument()

    view.rerender(<Harness onCancel={onCancel} onConfirm={onConfirm} />)
    await user.tab()
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus()
    await user.keyboard("{Escape}")
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it("returns focus to an enclosing trap without dismissing it", async () => {
    const user = userEvent.setup()
    const outerDeactivate = vi.fn()
    function OuterDialog() {
      const ref = useFocusTrap<HTMLDivElement>({
        active: true,
        onDeactivate: outerDeactivate,
      })
      return (
        <div ref={ref} role="dialog" aria-label="Outer dialog">
          <Harness />
        </div>
      )
    }
    render(<OuterDialog />)
    const opener = screen.getByRole("button", { name: "Open confirmation" })
    await waitFor(() => expect(opener).toHaveFocus())
    await user.click(opener)
    await waitFor(() => expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus())
    await user.keyboard("{Escape}")
    await waitFor(() => expect(opener).toHaveFocus())
    expect(outerDeactivate).not.toHaveBeenCalled()
    await user.tab()
    expect(screen.getByRole("button", { name: "Outside action" })).toHaveFocus()
    await user.tab()
    expect(opener).toHaveFocus()
  })
})
