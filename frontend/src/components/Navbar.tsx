import { Link, useNavigate, useLocation } from "react-router-dom"
import { useState, useEffect, useRef, useMemo, useCallback } from "react"
import Skeleton from "@mui/material/Skeleton"
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
import { useAppShell } from "@/contexts/AppShellContext"
import { getNavigationConfig } from "@/config/navigation"
import SettingsIcon from "@mui/icons-material/Settings"
import { cn } from "@/utils/cn"
import { MobileMenu } from "@/components/navbar/MobileMenu"
import { motion, useScroll, useMotionValueEvent } from "framer-motion"
import {
  hoverLift,
  springSoft,
  springBouncy,
  staggerContainerVariants,
  slideUpVariants,
  hoverScale,
} from "@/utils/animations"

const AVATAR_FALLBACK = AVATAR_PLACEHOLDER_URL

function parseCacheVersion(input: unknown): number | undefined {
  if (typeof input === "number" && Number.isFinite(input)) return input
  if (typeof input === "string") {
    const numeric = Number(input)
    if (!Number.isNaN(numeric)) return numeric
    const parsed = Date.parse(input)
    if (!Number.isNaN(parsed)) return parsed
  }
  return undefined
}

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
    const scrolled = latest > 20
    if (scrolled !== isScrolled) setIsScrolled(scrolled)
  })

  // Disable "scrolled" state on mobile to avoid layout shifts or too much blur
  const isMobile = useMediaQuery("(max-width: 1350px)")
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
      (user as any)?.avatar_updated_at ??
      (user as any)?.avatar_version ??
      (user as any)?.updated_at ??
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
          "navbar-root navbar-forced-white sticky top-0 z-[var(--ue-z-index-nav)] w-full flex flex-col justify-center",
          "border-b border-[var(--glass-border)] transition-all",
          isScrolled
            ? "bg-[var(--glass-bg)] shadow-glass backdrop-blur-[var(--glass-blur)] py-2"
            : "bg-transparent py-4",
          "min-h-[64px] items-center",
          prefersReducedMotion && "transition-none"
        )}
        style={{
          transitionDuration: "800ms",
          transitionTimingFunction: "var(--ease-premium, cubic-bezier(0.16, 1, 0.3, 1))",
        }}
      >
        <div className="flex h-full w-full items-center px-[clamp(16px,5vw,48px)] box-border">
          <Link
            to="/dashboard"
            aria-label={t("navigation:aria.homeLink")}
            className={cn(
              "brand inline-flex min-w-0 items-center rounded-2xl px-3 py-1.5 no-underline group transition-all duration-300 hover:bg-[var(--glass-tint-1)]",
              isMobile ? "gap-2.5" : "gap-4"
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
              className="flex items-center justify-center shrink-0 rounded-full bg-white shadow-md w-[clamp(32px,7vw,42px)] h-[clamp(32px,7vw,42px)] border border-white/60"
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
              <span
                className="whitespace-nowrap font-black tracking-tight text-[clamp(14px,3.5vw,18px)] group-hover:opacity-80 transition-all duration-300 leading-tight"
                style={{ color: "var(--nav-text)" }}
              >
                {t("navigation:brandName")}
              </span>
            </div>
          </Link>

          {isMobile ? (
            <div className="ml-auto flex items-center gap-[clamp(12px,3vw,24px)]">
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
                    className="block cursor-pointer rounded-full border-2 border-white/50 shadow-sm object-cover w-[clamp(28px,6vw,40px)] h-[clamp(28px,6vw,40px)] shrink-0"
                    onClick={() => go("/profile")}
                  />
                </motion.div>
              ) : (
                <Skeleton
                  variant="circular"
                  sx={{
                    bgcolor: "rgba(255,255,255,0.32)",
                    width: "clamp(28px, 6vw, 40px)",
                    height: "clamp(28px, 6vw, 40px)",
                  }}
                  aria-hidden="true"
                  className="shrink-0"
                />
              )}
              <motion.button
                whileTap={{ scale: 0.9 }}
                transition={springSoft}
                type="button"
                className="flex shrink-0 cursor-pointer items-center justify-center rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-tint2)] p-0 shadow-sm backdrop-blur-md transition-all duration-300 hover:bg-[var(--glass-tint1)]"
                style={{
                  width: "clamp(36px, 8vw, 44px)",
                  height: "clamp(36px, 8vw, 44px)",
                  color: "var(--nav-text)",
                }}
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
                  className="overflow-visible stroke-[var(--nav-text)] w-[20px] h-[20px]"
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
              <motion.ul
                variants={staggerContainerVariants(0.05, 0.2)}
                initial="hidden"
                animate="visible"
                className="ml-8 flex flex-1 flex-row flex-wrap items-center gap-1 m-0 p-0 min-w-0 list-none text-[1.05rem] font-medium"
              >
                {menuLinks.map((item) => (
                  <motion.li
                    key={item.to}
                    variants={slideUpVariants}
                    whileHover={{ y: -1 }}
                    whileTap={{ scale: 0.98 }}
                  >
                    <Link
                      to={item.to}
                      className={cn("menu-link", isActive(item.to) && "active")}
                      onPointerDown={markScrollFromBottom}
                      onClick={(e) => {
                        if (isSameTarget(item.to)) {
                          e.preventDefault()
                          scrollToTop(prefersReducedMotion ? "auto" : "smooth")
                        }
                      }}
                    >
                      <span className="relative z-10 transition-colors duration-200">
                        {item.label}
                      </span>
                      {isActive(item.to) && (
                        <motion.div
                          layoutId="navbar-active-bar"
                          className="active-bar"
                          transition={springSoft}
                        />
                      )}
                    </Link>
                  </motion.li>
                ))}
              </motion.ul>
              {loading ? (
                <div className="ml-auto flex items-center gap-3" aria-hidden="true">
                  <Skeleton
                    variant="circular"
                    width={40}
                    height={40}
                    sx={{ bgcolor: "rgba(255,255,255,0.25)" }}
                  />
                  <Skeleton
                    variant="text"
                    width={100}
                    height={24}
                    sx={{ bgcolor: "rgba(255,255,255,0.25)" }}
                  />
                </div>
              ) : (
                isAuth &&
                user && (
                  <motion.div
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.4, ...springSoft }}
                    className="ml-auto flex min-w-0 items-center gap-4 whitespace-nowrap"
                  >
                    <MessengerButton />
                    <NotificationsBell />
                    <div className="flex h-10 items-center gap-3 pl-4 border-l border-[var(--glass-border)] ml-2">
                      <motion.div
                        whileHover={{ scale: 1.05 }}
                        whileTap={{ scale: 0.95 }}
                        transition={springBouncy}
                      >
                        <SmartImage
                          srcRaw={hasAvatar ? avatarSource : avatarFallback}
                          cacheV={hasAvatar ? avatarCacheV : undefined}
                          fallback={avatarFallback}
                          alt={profileAlt}
                          title={profileTitle}
                          className="block h-9 w-9 cursor-pointer rounded-full border border-white/60 bg-white object-cover shadow-sm hover:shadow-md transition-all duration-300"
                          onClick={() => go("/profile")}
                        />
                      </motion.div>
                      <button
                        type="button"
                        onClick={() => go("/profile")}
                        aria-label={profileTitle}
                        title={profileTitle}
                        className="cursor-pointer border-none bg-transparent p-0 m-0 font-bold text-[var(--nav-text)] tracking-tight text-[1.05rem] hover:text-[var(--nav-link)] transition-colors"
                      >
                        {user.full_name}
                      </button>
                      <motion.button
                        whileHover={{
                          rotate: 90,
                          scale: 1.1,
                          backgroundColor: "var(--glass-tint-2)",
                        }}
                        whileTap={{ scale: 0.9 }}
                        transition={springSoft}
                        type="button"
                        className="flex items-center justify-center w-10 h-10 rounded-xl text-[var(--nav-text)] transition-colors"
                        onClick={() => go("/settings")}
                        aria-label={t("navigation:menu.settings")}
                        title={t("navigation:menu.settings")}
                      >
                        <SettingsIcon sx={{ fontSize: 24 }} />
                      </motion.button>
                    </div>
                  </motion.div>
                )
              )}
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
