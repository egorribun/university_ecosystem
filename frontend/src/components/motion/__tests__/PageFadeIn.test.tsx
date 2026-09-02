import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import PageFadeIn from "@/components/motion/PageFadeIn"

describe("PageFadeIn", () => {
  it("renders ready content with the default effect and delay", () => {
    render(
      <PageFadeIn>
        <span>content</span>
      </PageFadeIn>
    )

    const root = screen.getByText("content").parentElement!
    expect(root).toHaveAttribute("data-page-fade")
    expect(root).toHaveAttribute("data-ready", "true")
    expect(root).not.toHaveAttribute("data-effect")
    expect(root).toHaveStyle({ "--page-fade-delay": "100ms" })
  })

  it("applies the soft-blur effect and an explicit delay", () => {
    render(
      <PageFadeIn effect="soft-blur" delay={425}>
        <span>blurred content</span>
      </PageFadeIn>
    )

    const root = screen.getByText("blurred content").parentElement!
    expect(root).toHaveAttribute("data-effect", "soft-blur")
    expect(root).toHaveStyle({ "--page-fade-delay": "425ms" })
  })

  it("does not install production scheduling or media listeners in test mode", () => {
    const requestAnimationFrame = vi.spyOn(window, "requestAnimationFrame")
    const matchMedia = vi.spyOn(window, "matchMedia")

    render(<PageFadeIn>test-mode</PageFadeIn>)

    expect(requestAnimationFrame).not.toHaveBeenCalled()
    expect(matchMedia).not.toHaveBeenCalled()
  })
})
