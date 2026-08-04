import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)

import { FadeIn } from "@/components/ui/motion/FadeIn"

describe("FadeIn direction variants", () => {
  it.each(["down", "left", "right", "none"] as const)(
    "renders the %s initial variant",
    (direction) => {
      render(
        <FadeIn direction={direction} distance={12}>
          {direction}
        </FadeIn>
      )
      expect(screen.getByText(direction)).toBeInTheDocument()
    }
  )
})
