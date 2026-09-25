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

  it("shows every link inline on phones with an empty overflow menu", () => {
    const { result } = renderHook(() =>
      useNavbarMorph(links, { isScrolled: false, viewport: "phone", prefersReducedMotion: true })
    )

    expect(result.current).toMatchObject({
      isCompact: false,
      isPhone: true,
      isTablet: false,
      isDesktop: false,
      prefersReducedMotion: true,
    })
    expect(result.current.priorityLinks).toEqual(links)
    expect(result.current.overflowLinks).toEqual([])
  })

  it("reports exactly one active viewport flag for tablet and desktop", () => {
    const { result, rerender } = renderHook(
      ({ viewport }: { viewport: "tablet" | "desktop" }) =>
        useNavbarMorph(links, { isScrolled: false, viewport, prefersReducedMotion: false }),
      { initialProps: { viewport: "tablet" as "tablet" | "desktop" } }
    )

    expect(result.current).toMatchObject({ isPhone: false, isTablet: true, isDesktop: false })
    expect(result.current.priorityLinks).toEqual(links.slice(0, 4))

    rerender({ viewport: "desktop" })
    expect(result.current).toMatchObject({ isPhone: false, isTablet: false, isDesktop: true })
    expect(result.current.overflowLinks).toEqual(links.slice(6))
  })
})
