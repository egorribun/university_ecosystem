import { Link, useNavigate, useLocation } from "react-router-dom"
import { useState, useEffect, useRef, useMemo, useCallback } from "react"
import { useAuth } from "../contexts/AuthContext"
import guuLogo from "../assets/guu_logo.png"
import SmartImage from "@/components/SmartImage"
import NotificationsBell from "@/components/NotificationsBell"
import MessengerButton from "@/components/MessengerButton"
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders"
import { useTranslation } from "react-i18next"
import useMediaQuery from "@/hooks/useMediaQuery"
import useFocusTrap from "@/hooks/useFocusTrap"
import useScrollRestoration from "@/hooks/useScrollRestoration"
import { getNavigationConfig } from "@/config/navigation"
import { cn } from "@/utils/cn"
import { MobileMenu } from "@/components/navbar/MobileMenu"
import { DesktopNav } from "@/components/navbar/DesktopNav"
import { UserMenu } from "@/components/navbar/UserMenu"
import { motion, useScroll, useMotionValueEvent } from "framer-motion"
import { breakpoints } from "@/theme/tokens"
import {
  springSoft,
  hoverScale,
} from "@/utils/animations"
import { NAVBAR_SCROLL_THRESHOLD } from "@/constants/scroll"

import { parseCacheVersion } from "@/utils/cache"

const AVATAR_FALLBACK = AVATAR_PLACEHOLDER_URL

const Navbar = () => {
  const navigate = useNavigate()
  const location = useLocation()
  const pathname = location.pathname
  const { user, isAuth, loading } = useAuth()
  const { t } = useTranslation(["navigation"])

  const [mobileMenu, setMobileMenu] = useState(false)
  const [isScrolled, setIsScrolled] = useState(false)

  const { scrollY } = useScroll()
  useMotionValueEvent(scrollY, "change", (latest) => {
    const scrolled = latest > NAVBAR_SCROLL_THRESHOLD
    if (scrolled !== isScrolled) setIsScrolled(scrolled)
  })

  // Disable "scrolled" state on mobile to avoid layout shifts or too much blur
  const isMobile = useMediaQuery(`(max-width: ${breakpoints.wide})`)
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")
  const { scrollToTop, markScrollFromBottom, isSamePath } = useScrollRestoration(location.pathname)
  const prevIsMobile = useRef(isMobile)
  const navRef = useRef<HTMLElement | null>(null)
  const burgerBtnRef = useRef<HTMLButtonElement | null>(null)
  const drawerTrapRef = useFocusTrap<HTMLDivElement>({
    active: mobileMenu && isMobile,
    onDeactivate: () => setMobileMenu(false),
  })

  useEffect(() => {
    if (prevIsMobile.current !== isMobile && !isMobile) setMobileMenu(false)
    prevIsMobile.current = isMobile
  }, [isMobile])

  useEffect(() => {
    setMobileMenu(false)
  }, [location.pathname])

  const avatarCacheV = useMemo(() => {
    const raw =
      user?.avatar_updated_at ??
      user?.avatar_version ??
      user?.updated_at ??
      undefined
    return parseCacheVersion(raw)
  }, [user])

  const avatarFallback = AVATAR_FALLBACK
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
        navigate(to)
      }
    },
    [isSameTarget, markScrollFromBottom, navigate, prefersReducedMotion, scrollToTop]
  )

  return (
    <>
      <motion.nav
        ref={navRef}
        initial={{ y: -100, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
        className={cn(
          "sticky top-0 z-(--z-navbar) w-full flex flex-col justify-center",
          "border-b border-glass-border transition-all duration-500",
          isScrolled
            ? "bg-nav/80 shadow-glass backdrop-nav h-(--navbar-height-scrolled)"
            : "bg-transparent h-(--navbar-height)",
          "items-center",
          "pt-(--safe-area-top)",
          prefersReducedMotion && "transition-none"
        )}
      >
        <div className="flex h-full w-full items-center px-fluid-x box-border">
          <Link
            to="/dashboard"
            aria-label={t("navigation:aria.homeLink")}
            className={cn(
              "inline-flex min-w-0 items-center rounded-2xl px-3 py-1.5 no-underline group transition-all duration-300 hover:bg-(--bg-surface-hover)/30",
              isMobile ? "gap-fluid-gap" : "gap-4"
            )}
            onPointerDown={markScrollFromBottom}
            onClick={(e) => {
              if (isSameTarget("/dashboard")) {
                e.preventDefault()
                scrollToTop(prefersReducedMotion ? "auto" : "smooth")
              }
            }}
          >
            <motion.div
              variants={hoverScale}
              whileHover="hover"
              whileTap="tap"
              className="flex items-center justify-center shrink-0 rounded-full bg-(--bg-surface-raised) shadow-sm w-11 h-11 border border-border-subtle"
            >
              <SmartImage
                srcRaw={guuLogo}
                alt={t("navigation:brandAlt")}
                className="object-contain w-[65%] h-[65%]"
                loading="eager"
                fetchPriority="high"
                sizes="(min-width: 1351px) 44px, (min-width: 768px) 36px, 26px"
                responsiveWidths={[28, 48, 64]}
                decoding="async"
              />
            </motion.div>
            <div className="flex flex-col justify-center">
              <span className="whitespace-nowrap font-black tracking-tight text-lg group-hover:opacity-80 transition-all duration-300 leading-tight text-brand">
                {t("navigation:brandName")}
              </span>
            </div>
          </Link>

          {isMobile ? (
            <div className="ml-auto flex items-center gap-(--fluid-gap)">
              <MessengerButton />
              <NotificationsBell />
              {isAuth && user && !loading ? (
                <motion.div whileTap={{ scale: 0.95 }} transition={springSoft}>
                  <SmartImage
                    srcRaw={hasAvatar ? avatarSource : avatarFallback}
                    cacheV={hasAvatar ? avatarCacheV : undefined}
                    fallback={avatarFallback}
                    alt={profileAlt}
                    title={profileTitle}
                    className="block cursor-pointer rounded-full border-2 border-brand/50 shadow-sm object-cover w-9 h-9 shrink-0"
                    onClick={() => go("/profile")}
                  />
                </motion.div>
              ) : (
                <div className="rounded-full shrink-0 w-9 h-9 bg-brand/30 animate-pulse" />
              )}
              <motion.button
                whileTap={{ scale: 0.9 }}
                transition={springSoft}
                type="button"
                className="flex shrink-0 cursor-pointer items-center justify-center rounded-2xl border border-(--glass-border) bg-(--bg-surface-hover)/10 p-0 shadow-sm backdrop-blur-md transition-all duration-300 hover:bg-(--bg-surface-hover)/20 w-11 h-11 text-(--text-primary)"
                onClick={() => setMobileMenu((v) => !v)}
                aria-label={
                  mobileMenu ? t("navigation:aria.closeMenu") : t("navigation:aria.openMenu")
                }
                aria-expanded={mobileMenu}
                aria-controls="mobile-drawer"
                ref={burgerBtnRef}
              >
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                  className="overflow-visible stroke-(--text-primary) w-[20px] h-[20px]"
                >
                  <motion.line
                    x1="4"
                    y1="8"
                    x2="20"
                    y2="8"
                    animate={{
                      y: mobileMenu ? 4 : 0,
                      rotate: mobileMenu ? 45 : 0,
                    }}
                    transition={springSoft}
                  />
                  <motion.line
                    x1="4"
                    y1="12"
                    x2="20"
                    y2="12"
                    animate={{ opacity: mobileMenu ? 0 : 1 }}
                    transition={{ duration: 0.2 }}
                  />
                  <motion.line
                    x1="4"
                    y1="16"
                    x2="20"
                    y2="16"
                    animate={{
                      y: mobileMenu ? -4 : 0,
                      rotate: mobileMenu ? -45 : 0,
                    }}
                    transition={springSoft}
                  />
                </svg>
              </motion.button>
            </div>
          ) : (
            <>
              <DesktopNav
                menuLinks={menuLinks}
                isActive={isActive}
                isSameTarget={isSameTarget}
                scrollToTop={scrollToTop}
                markScrollFromBottom={markScrollFromBottom}
                prefersReducedMotion={prefersReducedMotion}
              />
              <UserMenu
                user={user}
                isAuth={!!isAuth}
                loading={loading}
                go={go}
                t={t}
              />
            </>
          )}
        </div>
      </motion.nav>

      {isMobile && (
        <MobileMenu
          isOpen={mobileMenu}
          onClose={() => setMobileMenu(false)}
          menuLinks={menuLinks}
          isActive={isActive}
          go={go}
          user={user}
          isAuth={!!isAuth}
          prefersReducedMotion={prefersReducedMotion}
          drawerTrapRef={drawerTrapRef}
        />
      )}
    </>
  )
}

export default Navbar






