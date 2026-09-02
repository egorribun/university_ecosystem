import { useMemo } from "react"
import type { NavigationItem } from "@/config/navigation"

/** Number of priority items visible on tablet before overflow */
const TABLET_PRIORITY_COUNT = 4
const DESKTOP_PRIORITY_COUNT = 6

export type NavbarViewport = "phone" | "tablet" | "desktop"

interface NavbarMorphOptions {
  isScrolled: boolean
  viewport: NavbarViewport
  prefersReducedMotion: boolean
}

export interface NavbarMorphState {
  /** Whether navbar is in compact pill mode (after scroll) */
  isCompact: boolean
  /** Whether on tablet (between mobile and wide) */
  isTablet: boolean
  /** Whether on phone (narrow mobile) */
  isPhone: boolean
  /** Whether on wide desktop */
  isDesktop: boolean
  /** Whether user prefers reduced motion */
  prefersReducedMotion: boolean
  /** Priority items shown in tablet mode */
  priorityLinks: NavigationItem[]
  /** Overflow items shown in tablet "more" menu */
  overflowLinks: NavigationItem[]
}

export function useNavbarMorph(
  menuLinks: NavigationItem[],
  { isScrolled, viewport, prefersReducedMotion }: NavbarMorphOptions
): NavbarMorphState {
  const isPhone = viewport === "phone"
  const isTablet = viewport === "tablet"
  const isCompact = isScrolled
  const priorityCount = isTablet ? TABLET_PRIORITY_COUNT : DESKTOP_PRIORITY_COUNT

  const priorityLinks = useMemo(
    () => (isPhone ? menuLinks : menuLinks.slice(0, priorityCount)),
    [isPhone, menuLinks, priorityCount]
  )

  const overflowLinks = useMemo(
    () => (isPhone ? [] : menuLinks.slice(priorityCount)),
    [isPhone, menuLinks, priorityCount]
  )

  return {
    isCompact,
    isTablet,
    isPhone,
    isDesktop: viewport === "desktop",
    prefersReducedMotion,
    priorityLinks,
    overflowLinks,
  }
}
