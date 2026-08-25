import { renderHook } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { Home } from "lucide-react"

import { useNavbarMorph } from "@/components/navbar/useNavbarMorph"
import type { NavigationItem } from "@/config/navigation"

const links: NavigationItem[] = Array.from({ length: 11 }, (_, index) => ({
  to: `/route-${index}`,
  label: `Route ${index}`,
  icon: Home,
}))

describe("useNavbarMorph", () => {
  it("keeps tablet and desktop overflow deterministic", () => {
    const initialProps: { viewport: "tablet" | "desktop" } = { viewport: "tablet" }
    const { result, rerender } = renderHook(
      ({ viewport }: { viewport: "tablet" | "desktop" }) =>
        useNavbarMorph(links, {
          isScrolled: true,
          viewport,
          prefersReducedMotion: false,
        }),
      { initialProps }
    )

    expect(result.current.isCompact).toBe(true)
    expect(result.current.priorityLinks).toHaveLength(4)
    expect(result.current.overflowLinks).toHaveLength(7)

    rerender({ viewport: "desktop" })
    expect(result.current.priorityLinks).toHaveLength(6)
    expect(result.current.overflowLinks).toHaveLength(5)
  })
})
