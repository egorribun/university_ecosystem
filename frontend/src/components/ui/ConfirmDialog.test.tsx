import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { axe } from "jest-axe"

import { ConfirmDialog } from "./ConfirmDialog"

/**
 * ConfirmDialog ARIA + interaction tests.
 *
 * The dialog must:
 *  - render with role="alertdialog" + aria-modal="true";
 *  - link aria-labelledby to the title and aria-describedby to the message;
 *  - render only when ``open`` is true;
 *  - call onCancel and onConfirm at the right buttons;
 *  - disable buttons + set aria-busy on the confirm button while loading;
 *  - return zero axe violations.
 */

const baseProps = {
  open: true,
  title: "Delete item?",
  message: "This cannot be undone.",
  confirmText: "Delete",
  cancelText: "Cancel",
  onConfirm: vi.fn(),
  onCancel: vi.fn(),
}

describe("ConfirmDialog — render gating", () => {
  it("renders nothing when open is false", () => {
    const { container } = render(<ConfirmDialog {...baseProps} open={false} />)
    expect(container.querySelector('[role="alertdialog"]')).toBeNull()
  })

  it("renders the dialog when open is true", () => {
    render(<ConfirmDialog {...baseProps} />)
    expect(screen.getByRole("alertdialog")).toBeInTheDocument()
  })
})

describe("ConfirmDialog — ARIA shape", () => {
  it("uses role=alertdialog with aria-modal", () => {
    render(<ConfirmDialog {...baseProps} />)
    const dialog = screen.getByRole("alertdialog")
    expect(dialog).toHaveAttribute("aria-modal", "true")
  })

  it("links aria-labelledby to the title and aria-describedby to the message", () => {
    render(<ConfirmDialog {...baseProps} />)
    const dialog = screen.getByRole("alertdialog")
    const labelId = dialog.getAttribute("aria-labelledby")
    const descId = dialog.getAttribute("aria-describedby")
    expect(labelId).toBeTruthy()
    expect(descId).toBeTruthy()

    // Both IDs resolve to actual elements with the right text.
    expect(document.getElementById(labelId!)).toHaveTextContent("Delete item?")
    expect(document.getElementById(descId!)).toHaveTextContent("This cannot be undone.")
  })
})

describe("ConfirmDialog — interactions", () => {
  it("calls onCancel when Cancel is clicked", async () => {
    const user = userEvent.setup()
    const onCancel = vi.fn()
    render(<ConfirmDialog {...baseProps} onCancel={onCancel} />)

    await user.click(screen.getByRole("button", { name: "Cancel" }))
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it("calls onConfirm when Confirm is clicked", async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()
    render(<ConfirmDialog {...baseProps} onConfirm={onConfirm} />)

    await user.click(screen.getByRole("button", { name: "Delete" }))
    expect(onConfirm).toHaveBeenCalledOnce()
  })
})

describe("ConfirmDialog — loading state", () => {
  it("disables both buttons and sets aria-busy on confirm while loading", () => {
    render(<ConfirmDialog {...baseProps} isLoading />)
    const cancel = screen.getByRole("button", { name: "Cancel" })
    const confirm = screen.getByRole("button", { name: "Delete" })

    expect(cancel).toBeDisabled()
    expect(confirm).toBeDisabled()
    expect(confirm).toHaveAttribute("aria-busy", "true")
  })

  it("does not invoke handlers while loading (buttons disabled)", async () => {
    const user = userEvent.setup()
    const onCancel = vi.fn()
    const onConfirm = vi.fn()
    render(<ConfirmDialog {...baseProps} isLoading onCancel={onCancel} onConfirm={onConfirm} />)

    // Disabled buttons silently swallow clicks in user-event.
    await user.click(screen.getByRole("button", { name: "Cancel" }))
    await user.click(screen.getByRole("button", { name: "Delete" }))
    expect(onCancel).not.toHaveBeenCalled()
    expect(onConfirm).not.toHaveBeenCalled()
  })
})

describe("ConfirmDialog — variants", () => {
  it("renders danger variant", () => {
    render(<ConfirmDialog {...baseProps} variant="danger" />)
    expect(screen.getByRole("alertdialog")).toBeInTheDocument()
  })

  it("renders warning variant", () => {
    render(<ConfirmDialog {...baseProps} variant="warning" />)
    expect(screen.getByRole("alertdialog")).toBeInTheDocument()
  })
})

describe("ConfirmDialog — accessibility", () => {
  it("has no axe violations", async () => {
    const { container } = render(<ConfirmDialog {...baseProps} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it("has no axe violations in danger variant", async () => {
    const { container } = render(<ConfirmDialog {...baseProps} variant="danger" />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
