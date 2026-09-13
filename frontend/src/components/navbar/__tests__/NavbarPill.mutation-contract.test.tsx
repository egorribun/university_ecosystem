import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { NavbarPill } from "@/components/navbar/NavbarPill"

const child = <span>navigation content</span>

describe("NavbarPill mutation contracts", () => {
  it("preserves the expanded pill geometry and transition contract", () => {
    const { container } = render(
      <NavbarPill isCompact={false} prefersReducedMotion={false}>
        {child}
      </NavbarPill>
    )
    const outer = container.firstElementChild as HTMLElement
    const content = outer.firstElementChild as HTMLElement

    expect(screen.getByText("navigation content")).toBeInTheDocument()
    expect(outer).toHaveClass(
      "flex",
      "w-full",
      "items-center",
      "box-border",
      "transition-[transform,opacity]",
      "duration-500",
      "ease-[var(--ease-premium)]",
      "h-full",
      "max-w-none",
      "rounded-none",
      "bg-transparent",
      "border",
      "border-transparent",
      "shadow-none",
      "px-fluid-x"
    )
    expect(content).toHaveClass("relative", "z-[1]", "flex", "w-full", "items-center")
    expect(content).not.toHaveClass("gap-0")
    expect(outer.querySelector('[aria-hidden="true"]')).toBeNull()
  })

  it("preserves the compact matte surface, gradient overlay, and content layering", () => {
    const { container } = render(
      <NavbarPill isCompact prefersReducedMotion={false}>
        {child}
      </NavbarPill>
    )
    const outer = container.firstElementChild as HTMLElement
    const content = outer.children[1] as HTMLElement
    const gradient = outer.querySelector('[aria-hidden="true"]') as HTMLElement

    expect(outer).toHaveClass(
      "relative",
      "mx-auto",
      "h-(--navbar-pill-h)",
      "max-w-(--navbar-pill-max-w)",
      "rounded-[var(--navbar-pill-radius)]",
      "bg-(--pill-bg)",
      "border",
      "border-(--pill-border)",
      "px-(--navbar-pill-px)",
      "duration-500"
    )
    expect(content).toHaveClass("relative", "z-[1]", "flex", "w-full", "items-center", "gap-0")
    expect(gradient).toHaveClass(
      "pointer-events-none",
      "absolute",
      "inset-0",
      "rounded-[inherit]",
      "z-0"
    )
    expect(gradient).toHaveAttribute("aria-hidden", "true")
    expect(gradient.style.background).toBe("var(--pill-gradient)")
  })

  it("uses a zero-duration transition in reduced-motion expanded and compact states", () => {
    const { container, rerender } = render(
      <NavbarPill isCompact={false} prefersReducedMotion>
        {child}
      </NavbarPill>
    )
    expect(container.firstElementChild).toHaveClass("duration-0")

    rerender(
      <NavbarPill isCompact prefersReducedMotion>
        {child}
      </NavbarPill>
    )
    expect(container.firstElementChild).toHaveClass("duration-0")
    expect(container.querySelector('[aria-hidden="true"]')).toBeInTheDocument()
  })
})
