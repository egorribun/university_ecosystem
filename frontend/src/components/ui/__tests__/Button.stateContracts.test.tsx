import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { Button } from "@/components/ui/Button"

describe("Button presentation and interaction states", () => {
  it("defaults to solid elevation and medium sizing while honoring explicit variants", () => {
    const { rerender } = render(<Button>Save changes</Button>)
    const button = screen.getByRole("button", { name: "Save changes" })
    expect(button).toBeEnabled()
    expect(button).toHaveClass("shadow-surface", "min-h-12", "px-5", "py-2.5")

    rerender(
      <Button variant="outline" size="sm">
        Save changes
      </Button>
    )
    expect(button).toHaveClass("border", "bg-transparent", "min-h-11", "px-3", "py-2")
    expect(button).not.toHaveClass("min-h-12", "px-5", "py-2.5")
  })

  it("expands to full width only while requested", () => {
    const { rerender } = render(<Button>Continue</Button>)
    const button = screen.getByRole("button", { name: "Continue" })
    expect(button).not.toHaveClass("w-full")

    rerender(<Button fullWidth>Continue</Button>)
    expect(button).toHaveClass("w-full")
    expect(button).toBeEnabled()

    rerender(<Button fullWidth={false}>Continue</Button>)
    expect(button).not.toHaveClass("w-full")
    expect(button).toHaveAccessibleName("Continue")
  })

  it("blocks pointer interaction while disabled and restores the enabled action", () => {
    const onClick = vi.fn()
    const { rerender } = render(
      <Button disabled onClick={onClick}>
        Save changes
      </Button>
    )
    const button = screen.getByRole("button", { name: "Save changes" })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute("aria-disabled", "true")
    expect(button).toHaveClass("pointer-events-none")
    fireEvent.click(button)
    expect(onClick).not.toHaveBeenCalled()

    rerender(<Button onClick={onClick}>Save changes</Button>)
    expect(button).toBeEnabled()
    expect(button).not.toHaveAttribute("aria-disabled")
    expect(button).not.toHaveClass("pointer-events-none")
    fireEvent.click(button)
    expect(onClick).toHaveBeenCalledOnce()
  })

  it("preserves the label and accessible name while loading, then reveals it again", () => {
    const onClick = vi.fn()
    const { rerender } = render(
      <Button loading onClick={onClick}>
        Save changes
      </Button>
    )
    const button = screen.getByRole("button", { name: "Save changes" })
    const label = screen.getByText("Save changes")
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute("aria-disabled", "true")
    expect(button).toHaveAttribute("aria-busy", "true")
    expect(button).toHaveClass("pointer-events-none")
    expect(label).toHaveClass("relative", "opacity-0")
    expect(button).toHaveAccessibleName("Save changes")
    fireEvent.click(button)
    expect(onClick).not.toHaveBeenCalled()

    rerender(<Button onClick={onClick}>Save changes</Button>)
    expect(screen.getByText("Save changes")).toBe(label)
    expect(label).toHaveClass("relative")
    expect(label).not.toHaveClass("opacity-0")
    expect(button).toBeEnabled()
    expect(button).not.toHaveAttribute("aria-disabled")
    expect(button).not.toHaveAttribute("aria-busy")
    expect(button).not.toHaveClass("pointer-events-none")
    expect(button).toHaveAccessibleName("Save changes")
    fireEvent.click(button)
    expect(onClick).toHaveBeenCalledOnce()
  })
})
