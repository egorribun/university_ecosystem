import { screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("@/hooks/ui/useSlidingIndicator", () => ({
  useSlidingIndicator: () => ({ left: 0, top: 0, width: 100, height: 50 }),
}))

vi.mock("@/hooks/useMediaQuery", () => ({
  default: () => true,
}))

import MobileBottomNav from "@/components/layout/MobileBottomNav"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

describe("MobileBottomNav reduced-motion closure", () => {
  it("renders a static active pill and label when reduced motion is preferred", async () => {
    await renderWithRouter({
      ui: () => <MobileBottomNav />,
      path: "/dashboard",
      initialPath: "/dashboard",
    })

    const pill = document.querySelector(".bottom-nav-pill") as HTMLElement
    expect(pill).toBeInTheDocument()
    expect(pill.style.transition).toBe("none")
    expect(screen.getByText("Home")).toBeInTheDocument()
  })
})
