import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

// Keep the motion contract observable without starting a spring animation. The
// production component still uses Framer Motion; this focused suite verifies
// that its state machine receives the correct values for every interaction.
vi.mock("framer-motion", () => ({
  m: {
    span: ({ animate, initial, transition, ...props }: Record<string, unknown>) => (
      <span
        {...props}
        data-animate={JSON.stringify(animate)}
        data-initial={JSON.stringify(initial)}
        data-transition={JSON.stringify(transition)}
      />
    ),
  },
}))

import { Switch } from "@/components/ui/Switch"

describe("Switch behavior contract", () => {
  it("starts idle, enters hover only when enabled, and leaves hover on exit", () => {
    const { container } = render(<Switch checked={false} aria-label="notifications" />)
    const input = screen.getByRole("switch", { name: "notifications" })
    const root = input.parentElement as HTMLElement
    const [focusRing, track, thumb] = Array.from(root.children) as HTMLElement[]

    expect(JSON.parse(track?.dataset.animate ?? "{}") as Record<string, unknown>).toMatchObject({
      borderColor: "var(--border-subtle)",
      backgroundColor: "var(--bg-surface)",
    })
    expect(JSON.parse(thumb?.dataset.animate ?? "{}") as Record<string, unknown>).toMatchObject({
      x: 0,
      scale: 1,
    })
    expect(focusRing).toHaveClass("scale-90", "opacity-0")

    fireEvent.mouseEnter(root)
    expect(JSON.parse(track?.dataset.animate ?? "{}") as Record<string, unknown>).toMatchObject({
      borderColor: "var(--primary-hover)",
      backgroundColor: "var(--bg-surface-hover)",
    })
    expect(JSON.parse(thumb?.dataset.animate ?? "{}") as Record<string, unknown>).toMatchObject({
      scale: 1.1,
    })

    fireEvent.mouseLeave(root)
    expect(JSON.parse(track?.dataset.animate ?? "{}") as Record<string, unknown>).toMatchObject({
      borderColor: "var(--border-subtle)",
      backgroundColor: "var(--bg-surface)",
    })
    expect(container.firstElementChild).toBe(root)
  })

  it("keeps the checked track and thumb positions distinct", () => {
    const { container } = render(<Switch checked aria-label="enabled" className="custom-switch" />)
    const input = screen.getByRole("switch", { name: "enabled" })
    const root = input.parentElement as HTMLElement
    const [, track, thumb] = Array.from(root.children) as HTMLElement[]

    expect(root).toHaveClass("custom-switch")
    expect(JSON.parse(track?.dataset.animate ?? "{}") as Record<string, unknown>).toMatchObject({
      borderColor: "var(--primary-main)",
      backgroundColor: "color-mix(in srgb, var(--primary-main) 15%, transparent)",
    })
    expect(JSON.parse(thumb?.dataset.animate ?? "{}") as Record<string, unknown>).toMatchObject({
      x: 28,
      scale: 1,
    })
    expect(thumb).toHaveStyle({ transformOrigin: "left center" })
    expect(container.firstElementChild).toHaveClass("relative", "inline-flex", "min-h-11")
  })

  it("shows and restores the keyboard focus ring", () => {
    render(<Switch checked={false} aria-label="focusable" />)
    const input = screen.getByRole("switch", { name: "focusable" })
    const focusRing = input.parentElement?.firstElementChild
    expect(focusRing).toHaveClass("scale-90", "opacity-0")

    fireEvent.focus(input)
    expect(focusRing).toHaveClass("scale-100", "opacity-100", "ring-4")
    fireEvent.blur(input)
    expect(focusRing).toHaveClass("scale-90", "opacity-0")
  })

  it("does not throw when the optional change callback is omitted", () => {
    render(<Switch checked={false} aria-label="without callback" />)
    expect(() =>
      fireEvent.click(screen.getByRole("switch", { name: "without callback" }))
    ).not.toThrow()
  })

  it("does not enter hover state while disabled", () => {
    render(<Switch checked={false} disabled aria-label="disabled" />)
    const input = screen.getByRole("switch", { name: "disabled" })
    const root = input.parentElement as HTMLElement
    const [, track, thumb] = Array.from(root.children) as HTMLElement[]

    fireEvent.mouseEnter(root)
    expect(JSON.parse(track?.dataset.animate ?? "{}") as Record<string, unknown>).toMatchObject({
      borderColor: "var(--border-subtle)",
      backgroundColor: "var(--bg-surface)",
    })
    expect(JSON.parse(thumb?.dataset.animate ?? "{}") as Record<string, unknown>).toMatchObject({
      scale: 1,
    })
  })
})
