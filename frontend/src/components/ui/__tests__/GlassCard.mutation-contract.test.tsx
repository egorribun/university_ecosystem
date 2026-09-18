import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { GlassCard } from "@/components/ui/GlassCard"

describe("GlassCard mutation contracts", () => {
  it("renders the default glass surface, sheen layer, content layer, and DOM props", () => {
    render(
      <GlassCard data-testid="glass-card" className="custom-glass" aria-label="Glass panel">
        <span>Panel content</span>
      </GlassCard>
    )

    const card = screen.getByTestId("glass-card")
    expect(card).toHaveAttribute("aria-label", "Glass panel")
    expect(card).toHaveClass(
      "glass-noise",
      "relative",
      "overflow-hidden",
      "rounded-xl",
      "border",
      "border-glass-border",
      "shadow-glass",
      "transition-all",
      "duration-premium",
      "bg-glass",
      "backdrop-blur-xl",
      "custom-glass"
    )
    expect(card.querySelector(".pointer-events-none")).toHaveClass(
      "absolute",
      "inset-0",
      "bg-linear-to-br",
      "from-white/(--opacity-subtle)",
      "via-transparent",
      "to-transparent",
      "opacity-medium"
    )
    expect(card.querySelector(".relative.z-surface")).toContainElement(
      screen.getByText("Panel content")
    )
  })

  it.each([
    ["low", ["bg-(--glass-bg-low)", "dark:bg-(--glass-bg-low-dark)", "backdrop-blur-md"]],
    ["medium", ["bg-glass", "backdrop-blur-xl"]],
    ["high", ["bg-(--glass-bg-high)", "backdrop-blur-2xl"]],
    ["elevated", ["bg-glass-elevated", "backdrop-blur-2xl", "shadow-premium"]],
  ] as const)("applies the %s intensity variant", (intensity, expectedClasses) => {
    render(
      <GlassCard data-testid={`glass-${intensity}`} intensity={intensity}>
        {intensity}
      </GlassCard>
    )
    expect(screen.getByTestId(`glass-${intensity}`)).toHaveClass(...expectedClasses)
  })

  it.each([
    ["none", "rounded-none"],
    ["sm", "rounded-sm"],
    ["md", "rounded-md"],
    ["lg", "rounded-lg"],
    ["xl", "rounded-xl"],
    ["2xl", "rounded-2xl"],
    ["3xl", "rounded-3xl"],
  ] as const)("applies the %s radius variant", (radius, expectedClass) => {
    render(
      <GlassCard data-testid={`radius-${radius}`} radius={radius}>
        {radius}
      </GlassCard>
    )
    expect(screen.getByTestId(`radius-${radius}`)).toHaveClass(expectedClass)
  })

  it("adds interactive affordances only when requested", () => {
    const { rerender } = render(
      <GlassCard data-testid="interactive" interactive>
        Interactive
      </GlassCard>
    )
    const card = screen.getByTestId("interactive")
    expect(card).toHaveClass("card-hover-lift", "hover:bg-glass-tint1", "cursor-pointer")

    rerender(
      <GlassCard data-testid="interactive" interactive={false}>
        Static
      </GlassCard>
    )
    expect(card).not.toHaveClass("card-hover-lift", "hover:bg-glass-tint1", "cursor-pointer")
  })
})
