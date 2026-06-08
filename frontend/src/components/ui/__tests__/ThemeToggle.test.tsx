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
})
