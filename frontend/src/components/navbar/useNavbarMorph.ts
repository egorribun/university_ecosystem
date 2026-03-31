import { useMemo } from "react"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"
import { useScrollBehavior } from "@/hooks/ui/useScrollBehavior"
import type { NavigationItem } from "@/config/navigation"

/** Number of priority items visible on tablet before overflow */
const TABLET_PRIORITY_COUNT = 4

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

export function useNavbarMorph(menuLinks: NavigationItem[]): NavbarMorphState {
  const isPhone = useMediaQuery(`(max-width: ${breakpoints.small})`)
  const isMobile = useMediaQuery(`(max-width: ${breakpoints.wide})`)
  const isTabletRange = useMediaQuery(
    `(min-width: ${breakpoints.small}) and (max-width: ${breakpoints.wide})`
  )
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")
  const { isScrolled } = useScrollBehavior()

  // Compact pill activates on scroll for all breakpoints
  const isCompact = isScrolled

  const priorityLinks = useMemo(
    () => (isTabletRange ? menuLinks.slice(0, TABLET_PRIORITY_COUNT) : menuLinks),
    [isTabletRange, menuLinks]
  )

  const overflowLinks = useMemo(
    () => (isTabletRange ? menuLinks.slice(TABLET_PRIORITY_COUNT) : []),
    [isTabletRange, menuLinks]
  )

  return {
    isCompact,
    isTablet: isTabletRange,
    isPhone,
    isDesktop: !isMobile,
    prefersReducedMotion,
    priorityLinks,
    overflowLinks,
  }
}
