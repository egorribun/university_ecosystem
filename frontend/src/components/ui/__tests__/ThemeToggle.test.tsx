import { describe, expect, it, vi } from "vitest"
import { cleanup, fireEvent, screen } from "@testing-library/react"

import { ThemeToggle } from "@/components/ui/ThemeToggle"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

describe("ThemeToggle", () => {
  it("invokes onToggle when the button is clicked", async () => {
    const onToggle = vi.fn()
    await renderWithRouter({
      ui: () => <ThemeToggle isDark={false} onToggle={onToggle} />,
      authProvider: false,
    })
    fireEvent.click(screen.getByRole("button"))
    expect(onToggle).toHaveBeenCalledTimes(1)
  })

  it("flips the aria-label between light and dark modes (+ sm size)", async () => {
    await renderWithRouter({
      ui: () => <ThemeToggle isDark={false} onToggle={() => {}} />,
      authProvider: false,
    })
    const lightLabel = screen.getByRole("button").getAttribute("aria-label")
    cleanup()
    await renderWithRouter({
      ui: () => <ThemeToggle isDark onToggle={() => {}} size="sm" />,
      authProvider: false,
    })
    const darkLabel = screen.getByRole("button").getAttribute("aria-label")
    expect(lightLabel).toBeTruthy()
    expect(darkLabel).toBeTruthy()
    expect(darkLabel).not.toBe(lightLabel)
  })

  it.each([
    { size: "sm" as const, iconClasses: ["h-4", "w-4"] },
    { size: "md" as const, iconClasses: ["h-5", "w-5"] },
  ])(
    "keeps the $size target at least 44px without enlarging its glyph",
    async ({ size, iconClasses }) => {
      await renderWithRouter({
        ui: () => <ThemeToggle isDark={false} onToggle={() => {}} size={size} />,
        authProvider: false,
      })

      const button = screen.getByRole("button")
      expect(button).toHaveClass("min-h-11", "min-w-11")
      expect(button.querySelector("svg")).toHaveClass(...iconClasses)
    }
  )
})
