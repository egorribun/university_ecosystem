import { useEffect, useMemo, useState } from "react"
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
  // Wave 167 SW2 (Tier 1 Path B within-iter sub-fix per W138 Lesson #1) —
  // same mounted-state pattern as useNavbarLogic.ts (sibling hook). Pre-W167
  // SW2 these 4 `useMediaQuery()` calls (rawIsPhone + rawIsMobile +
  // rawIsTabletRange + rawPrefersReducedMotion) returned SSR defaults
  // (`false` × 4) vs CSR browser values, causing `priorityLinks` /
  // `overflowLinks` slicing (lines 39-47 post-edit) to diverge → DesktopNav
  // received different `menuLinks` count SSR vs CSR → `<ul>` `<li>` children
  // count diverged → React #418 hydration mismatch. Verified empirically
  // W167 SW2 via Path B NODE_ENV=development build wave165-admin-visual-
  // smoke.mjs re-run on /admin/audit_light sidecar (admin user has more
  // menu items → exceeds TABLET_PRIORITY_COUNT=4 threshold → overflow
  // logic active → DesktopNav <li> count diverges if isTabletRange differs).
  // Server + client first render both see `mounted=false` → both safely
  // default to desktop layout (rawIsTabletRange=false → priorityLinks=full).
  // useEffect post-hydration → setMounted(true) → re-render with real values.
  const [mounted, setMounted] = useState(false)
  const rawIsPhone = useMediaQuery(`(max-width: ${breakpoints.small})`)
  const rawIsMobile = useMediaQuery(`(max-width: ${breakpoints.wide})`)
  const rawIsTabletRange = useMediaQuery(
    `(min-width: ${breakpoints.small}) and (max-width: ${breakpoints.wide})`
  )
  const rawPrefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")
  useEffect(() => {
    setMounted(true)
  }, [])
  const isPhone = mounted ? rawIsPhone : false
  const isMobile = mounted ? rawIsMobile : false
  const isTabletRange = mounted ? rawIsTabletRange : false
  const prefersReducedMotion = mounted ? rawPrefersReducedMotion : false
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
