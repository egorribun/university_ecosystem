import { useState, useEffect, useRef, useMemo, useCallback } from "react"
import { useNavigate, useRouterState } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"

import { useAuth } from "@/contexts/AuthContext"
import useMediaQuery from "@/hooks/useMediaQuery"
import useFocusTrap from "@/hooks/useFocusTrap"
import useScrollRestoration from "@/hooks/useScrollRestoration"
import { breakpoints } from "@/theme/tokens"

import { getNavigationConfig } from "@/config/navigation"
import { parseCacheVersion } from "@/utils/cache"
import { useScrollBehavior } from "@/hooks/ui/useScrollBehavior"
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders"

export type NavbarLogicResult = ReturnType<typeof useNavbarLogic>

export const useNavbarLogic = () => {
  const navigate = useNavigate()
  const pathname = useRouterState({ select: (s) => s.location.pathname })
  const { user, isAuth, loading } = useAuth()
  const { t } = useTranslation(["navigation"])

  const [mobileMenuStart, setMobileMenuStart] = useState(false)
  // Scroll behavior
  const { isScrolled } = useScrollBehavior()

  // Wave 167 SW2 (Tier 1 Path B) — mounted-state pattern (W156 SW3
  // LiveRegionProvider canonical at frontend/src/components/ui/
  // LiveRegionProvider.tsx:50-115, W166 SW2 applied to AdminLayout at
  // _admin.tsx:30-51) closes the React #418 hydration mismatch caused by
  // these two `useMediaQuery()` calls returning SSR defaults (`false` +
  // `false`) vs CSR browser values (`true` on narrow viewports / under
  // prefers-reduced-motion). Pre-W167 SW2, `isMobile` divergence
  // cascaded through Navbar.tsx:91 `{isMobile && <MobileMenu>}` (fragment
  // child count differs server vs client), NavbarActions.tsx:43
  // `if (isMobile) ... <div> ... else ... <ul>` (element-type swap),
  // and multiple subcomponents receiving `isMobile` + `prefersReducedMotion`
  // props (NavbarLogo, NavbarPill, NavbarActions, DesktopNav, UserMenu,
  // NavbarOverflowMenu). Verified empirically W167 SW2 via Path B
  // NODE_ENV=development build wave165-admin-visual-smoke.mjs re-run:
  // dev React bundle emitted full unminified error message with diff
  // showing `<ul>` (server) vs `<div>` (client) for NavbarActions
  // root element on /admin/audit_light sidecar.
  //
  // Standard pattern: server + client first render both see `mounted=false`
  // → both pass safe defaults (matching DOM output). useEffect fires
  // post-hydration → setMounted(true) triggers re-render with real hook
  // values. Single-frame visual flicker on mobile (~16ms at 60fps) is
  // imperceptible and acceptable per W156 SW3 trade-off.
  //
  // Because Navbar mounts on EVERY non-compact route (not just /admin/*),
  // this fix benefits all SSR-rendered authenticated routes (W128+ SSR
  // arc covered /dashboard + /events + /news + /schedule + /profile +
  // /settings — same React #418 was firing × 2 there too but smoke was
  // admin-scoped per W165 SW3).
  const [mounted, setMounted] = useState(false)
  // Disable "scrolled" state on mobile to avoid layout shifts or too much blur
  const rawIsMobile = useMediaQuery(`(max-width: ${breakpoints.wide})`)
  const rawPrefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")
  useEffect(() => {
    setMounted(true)
  }, [])
  // Server + client initial render: pass defaults (mounted=false branch).
  // After hydration: useEffect → re-render with actual hook values.
  const isMobile = mounted ? rawIsMobile : false
  const prefersReducedMotion = mounted ? rawPrefersReducedMotion : false
  const { scrollToTop, markScrollFromBottom, isSamePath } = useScrollRestoration(pathname)
  const prevIsMobile = useRef(isMobile)
  const navRef = useRef<HTMLElement | null>(null)
  const burgerBtnRef = useRef<HTMLButtonElement | null>(null)

  // Mobile menu focus trap
  const drawerTrapRef = useFocusTrap<HTMLDivElement>({
    active: mobileMenuStart && isMobile,
    onDeactivate: () => setMobileMenuStart(false),
  })

  useEffect(() => {
    if (prevIsMobile.current !== isMobile && !isMobile) setMobileMenuStart(false)
    prevIsMobile.current = isMobile
  }, [isMobile])

  useEffect(() => {
    setMobileMenuStart(false)
  }, [pathname])

  const avatarCacheV = useMemo(() => {
    const raw = user?.avatar_updated_at ?? user?.avatar_version ?? user?.updated_at ?? undefined
    return parseCacheVersion(raw)
  }, [user])

  const avatarFallback = AVATAR_PLACEHOLDER_URL
  const avatarSource = user?.avatar_url || ""
  const hasAvatar = Boolean(avatarSource)

  const menuLinks = useMemo(() => {
    return getNavigationConfig(t, user?.role)
  }, [t, user?.role])

  const profileAlt = user?.full_name
    ? t("navigation:aria.profileAvatarNamed", { name: user.full_name })
    : t("navigation:aria.profileAvatar")
  const profileTitle = t("navigation:aria.openProfile")

  const isActive = useCallback(
    (to: string) => {
      if (to === "/dashboard") {
        return pathname === "/" || pathname === "/dashboard" || pathname.startsWith("/dashboard/")
      }
      return pathname === to
    },
    [pathname]
  )

  const isSameTarget = useCallback((to: string) => isSamePath(to), [isSamePath])

  const go = useCallback(
    (to: string) => {
      if (isSameTarget(to)) {
        scrollToTop(prefersReducedMotion ? "auto" : "smooth")
      } else {
        markScrollFromBottom()
        navigate({ to })
      }
    },
    [isSameTarget, markScrollFromBottom, navigate, prefersReducedMotion, scrollToTop]
  )

  return {
    mobileMenu: mobileMenuStart,
    setMobileMenu: setMobileMenuStart,
    isScrolled,
    isMobile,
    prefersReducedMotion,
    scrollToTop,
    markScrollFromBottom,
    isSameTarget,
    go,
    navRef,
    burgerBtnRef,
    drawerTrapRef,
    avatarCacheV,
    avatarFallback,
    avatarSource,
    hasAvatar,
    menuLinks,
    profileAlt,
    profileTitle,
    isActive,
    user,
    isAuth,
    loading,
    t,
  }
}
