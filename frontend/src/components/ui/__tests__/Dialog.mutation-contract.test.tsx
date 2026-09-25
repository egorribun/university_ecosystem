import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

const focusTrap = vi.hoisted(() => ({
  options: null as Record<string, unknown> | null,
}))

vi.mock("@/hooks/useFocusTrap", () => ({
  default: (options: Record<string, unknown>) => {
    focusTrap.options = options
    return { current: null }
  },
}))

import { Dialog, shouldRenderDialog } from "@/components/ui/Dialog"

afterEach(() => {
  cleanup()
  focusTrap.options = null
})

describe("Dialog mutation contracts", () => {
  it("keeps the default and explicit size classes observable", async () => {
    const view = render(
      <Dialog open onClose={vi.fn()} title="Default size">
        body
      </Dialog>
    )

    const defaultDialog = await screen.findByRole("dialog", { name: "Default size" })
    expect(defaultDialog).toHaveClass("relative", "z-surface", "w-full", "max-w-(--dialog-max-w)")
    expect(defaultDialog).toHaveClass("sm:max-w-[32rem]", "focus:outline-none")
    expect(defaultDialog).toHaveClass("glass-layer-elevated")
    expect(defaultDialog).not.toHaveClass("h-dvh")
    expect(defaultDialog).not.toHaveAttribute("aria-describedby")

    view.rerender(
      <Dialog open onClose={vi.fn()} title="Small size" size="sm">
        body
      </Dialog>
    )
    expect(await screen.findByRole("dialog", { name: "Small size" })).toHaveClass(
      "sm:max-w-[24rem]"
    )

    view.rerender(
      <Dialog open onClose={vi.fn()} title="Large size" size="lg">
        body
      </Dialog>
    )
    expect(await screen.findByRole("dialog", { name: "Large size" })).toHaveClass(
      "sm:max-w-[42rem]"
    )
  })

  it("preserves full-screen mobile classes and custom body/footer geometry", async () => {
    render(
      <Dialog
        open
        onClose={vi.fn()}
        title="Full screen"
        fullScreenOnMobile
        bodyClassName="body-contract"
        footerClassName="footer-contract"
        footer={<button type="button">Apply</button>}
      >
        content
      </Dialog>
    )

    const dialog = await screen.findByRole("dialog", { name: "Full screen" })
    expect(dialog).toHaveClass("h-dvh", "max-h-dvh", "rounded-none", "bg-(--bg-surface)")
    expect(dialog).not.toHaveClass("glass-layer-elevated")
    expect(dialog.querySelector(".body-contract")).toHaveClass("mt-5", "space-y-5")
    expect(dialog.querySelector(".footer-contract")).toHaveClass(
      "mt-6",
      "flex",
      "flex-col",
      "gap-3",
      "sm:flex-row",
      "sm:justify-end"
    )
  })

  it("passes the default focus callback and preserves an explicit false policy", async () => {
    render(
      <Dialog open onClose={vi.fn()} title="Focus callback">
        content
      </Dialog>
    )
    const defaultClose = await screen.findByRole("button", { name: "Close" })
    expect(focusTrap.options?.active).toBe(true)
    expect(focusTrap.options?.allowOutsideClick).toBe(true)
    expect(focusTrap.options?.initialFocus).toBeTypeOf("function")
    expect((focusTrap.options?.initialFocus as () => unknown)()).toBe(defaultClose)

    cleanup()
    focusTrap.options = null
    render(
      <Dialog open onClose={vi.fn()} title="No initial focus" initialFocus={false}>
        content
      </Dialog>
    )
    await screen.findByRole("dialog", { name: "No initial focus" })
    const secondOptions = focusTrap.options as Record<string, unknown> | null
    expect(secondOptions?.initialFocus).toBe(false)
  })

  it("creates one portal root, keeps it stable across rerenders, and removes it on unmount", async () => {
    const view = render(
      <Dialog open onClose={vi.fn()} title="Stable portal">
        content
      </Dialog>
    )
    await screen.findByRole("dialog", { name: "Stable portal" })
    expect(document.querySelectorAll('[data-dialog-root="true"]')).toHaveLength(1)

    view.rerender(
      <Dialog open onClose={vi.fn()} title="Stable portal">
        updated
      </Dialog>
    )
    expect(screen.getByText("updated")).toBeInTheDocument()
    expect(document.querySelectorAll('[data-dialog-root="true"]')).toHaveLength(1)

    view.unmount()
    expect(document.querySelectorAll('[data-dialog-root="true"]')).toHaveLength(0)
  })

  it("owns the portal root only while open", async () => {
    const view = render(
      <Dialog open onClose={vi.fn()} title="Toggleable">
        content
      </Dialog>
    )
    await screen.findByRole("dialog", { name: "Toggleable" })
    expect(document.querySelectorAll('[data-dialog-root="true"]')).toHaveLength(1)

    view.rerender(
      <Dialog open={false} onClose={vi.fn()} title="Toggleable">
        content
      </Dialog>
    )
    await waitFor(() => {
      expect(document.querySelectorAll('[data-dialog-root="true"]')).toHaveLength(0)
    })
  })

  it("updates labelled and described references when content is added after mount", async () => {
    const view = render(
      <Dialog open onClose={vi.fn()} ariaLabel="Untitled">
        content
      </Dialog>
    )
    const dialog = await screen.findByRole("dialog", { name: "Untitled" })
    expect(dialog).not.toHaveAttribute("aria-labelledby")
    expect(dialog).not.toHaveAttribute("aria-describedby")

    view.rerender(
      <Dialog open onClose={vi.fn()} title="Added title" subtitle="Added subtitle">
        content
      </Dialog>
    )
    await waitFor(() => {
      expect(screen.getByRole("dialog", { name: "Added title" })).toHaveAttribute("aria-labelledby")
    })
    expect(screen.getByRole("dialog", { name: "Added title" })).toHaveAttribute("aria-describedby")
  })

  it.each([
    [true, document.createElement("div"), true],
    [true, null, false],
    [false, document.createElement("div"), false],
  ] as const)("keeps the portal renderability contract for open=%s", (open, node, expected) => {
    expect(shouldRenderDialog(open, node)).toBe(expected)
  })
})
