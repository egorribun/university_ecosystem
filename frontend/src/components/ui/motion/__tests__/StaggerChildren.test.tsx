import { afterEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"

import { StaggerChildren } from "@/components/ui/motion/StaggerChildren"

// matchMedia + IntersectionObserver are polyfilled in setupTests.ts.

describe("StaggerChildren", () => {
  afterEach(() => vi.restoreAllMocks())

  it("renders children + attaches an IntersectionObserver (motion enabled)", () => {
    render(
      <StaggerChildren className="grid">
        <div className="stagger-item">A</div>
      </StaggerChildren>
    )
    expect(screen.getByText("A")).toBeInTheDocument()
  })

  it("marks stagger items visible immediately under reduced motion", () => {
    vi.spyOn(window, "matchMedia").mockReturnValue({
      matches: true,
      media: "(prefers-reduced-motion: reduce)",
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    } as unknown as MediaQueryList)

    const { container } = render(
      <StaggerChildren>
        <div className="stagger-item">B</div>
      </StaggerChildren>
    )
    const item = container.querySelector<HTMLElement>(".stagger-item")
    expect(item?.dataset.visible).toBe("true")
  })
})
