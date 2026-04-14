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

  // Disable "scrolled" state on mobile to avoid layout shifts or too much blur
  const isMobile = useMediaQuery(`(max-width: ${breakpoints.wide})`)
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")
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
