import { describe, expect, it } from "vitest"
import { screen } from "@testing-library/react"

import { ScaleIn } from "@/components/ui/motion/ScaleIn"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

// m.div wrapper — renderWithRouter supplies the LazyMotion(domAnimation) context.

describe("ScaleIn", () => {
  it("renders its children", async () => {
    await renderWithRouter({
      ui: () => (
        <ScaleIn>
          <span>scaled content</span>
        </ScaleIn>
      ),
      authProvider: false,
    })
    expect(screen.getByText("scaled content")).toBeInTheDocument()
  })

  it("forwards className + custom timing props (variants build path)", async () => {
    const { container } = await renderWithRouter({
      ui: () => (
        <ScaleIn className="sc" delay={0.1} duration={0.2} initialScale={0.5}>
          <span>x</span>
        </ScaleIn>
      ),
      authProvider: false,
    })
    expect(container.querySelector(".sc")).not.toBeNull()
  })
})
