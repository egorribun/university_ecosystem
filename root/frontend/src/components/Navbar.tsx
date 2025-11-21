import { Link, useNavigate, useLocation } from "react-router-dom"
import { useState, useEffect, useRef, useMemo, useCallback } from "react"
import Skeleton from "@mui/material/Skeleton"
import { useAuth } from "../contexts/AuthContext"
import guuLogo from "../assets/guu_logo.png"
import SmartImage from "@/components/SmartImage"
import NotificationsBell from "@/components/NotificationsBell"
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders"
import { useTranslation } from "react-i18next"
import useMediaQuery from "@/hooks/useMediaQuery"
import useFocusTrap from "@/hooks/useFocusTrap"
import useScrollRestoration from "@/hooks/useScrollRestoration"
import { useAppShell } from "@/contexts/AppShellContext"

const AVATAR_FALLBACK = AVATAR_PLACEHOLDER_URL

const navTextColor = "var(--nav-text)"
const navBgColor = "var(--nav-bg)"

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
  const { user, isAuth, loading } = useAuth()
  const { t } = useTranslation(["navigation"])
  const { setOverlayState } = useAppShell()

  const [mobileMenu, setMobileMenu] = useState(false)

  const isMobile = useMediaQuery("(max-width: 1350px)")
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")
  const { scrollToTop, markScrollFromBottom, isSamePath } = useScrollRestoration(location.pathname)
  const prevIsMobile = useRef(isMobile)
  const navRef = useRef<HTMLDivElement | null>(null)
  const burgerBtnRef = useRef<HTMLButtonElement | null>(null)
  const closeButtonRef = useRef<HTMLButtonElement | null>(null)
  const drawerTrapRef = useFocusTrap<HTMLDivElement>({
    active: mobileMenu && isMobile,
    initialFocus: () => (closeButtonRef.current ?? navRef.current ?? document.body)!,
    fallbackFocus: () => (closeButtonRef.current ?? navRef.current ?? document.body)!,
    onDeactivate: () => setMobileMenu(false),
  })

  useEffect(() => {
    if (prevIsMobile.current !== isMobile && !isMobile) setMobileMenu(false)
    prevIsMobile.current = isMobile
  }, [isMobile])

  useEffect(() => {
    setMobileMenu(false)
  }, [location.pathname])

  useEffect(() => {
    if (mobileMenu && isMobile) {
      setOverlayState("mobile-drawer", { scrollLocked: true, blurred: !prefersReducedMotion })
    } else {
      setOverlayState("mobile-drawer", null)
    }
    return () => {
      setOverlayState("mobile-drawer", null)
    }
  }, [isMobile, mobileMenu, prefersReducedMotion, setOverlayState])

  useEffect(() => {
    if (prefersReducedMotion) return
    navRef.current?.classList.add("navbar-animate-in")
  }, [prefersReducedMotion])

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
    const base = [
      { to: "/dashboard", label: t("navigation:menu.dashboard") },
      { to: "/news", label: t("navigation:menu.news") },
      { to: "/schedule", label: t("navigation:menu.schedule") },
      { to: "/events", label: t("navigation:menu.events") },
      { to: "/activity", label: t("navigation:menu.activity") },
      { to: "/map", label: t("navigation:menu.map") },
    ]
    if (user?.role === "admin") {
      base.push({ to: "/admin/notifications", label: t("navigation:menu.notificationsAdmin") })
      base.push({ to: "/admin/stories", label: t("navigation:menu.stories") })
      base.push({ to: "/admin/users", label: t("navigation:menu.users") })
    }
    return base
  }, [t, user?.role])

  const profileAlt = user?.full_name
    ? t("navigation:aria.profileAvatarNamed", { name: user.full_name })
    : t("navigation:aria.profileAvatar")
  const profileTitle = t("navigation:aria.openProfile")

  const isActive = (to: string) => {
    if (to === "/dashboard" && location.pathname === "/") return true
    return location.pathname === to || location.pathname.startsWith(to + "/")
  }

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

  const logoWrapSize = isMobile ? 44 : 52
  const logoImgSize = isMobile ? 34 : 42
  const titleFont = isMobile ? "clamp(16px, 5.2vw, 20px)" : "clamp(18px, 1.6vw, 22px)"
  const rightNameFont = isMobile ? "clamp(14px, 4.5vw, 16px)" : "1.01rem"
  const avatarSize = isMobile ? "clamp(30px, 8vw, 36px)" : "36px"
  const burgerBtnSize = isMobile ? "clamp(44px, 10.5vw, 48px)" : "40px"
  const burgerIcon = isMobile ? 26 : 28

  return (
    <>
      <nav
        ref={navRef}
        className="navbar-root"
        style={{
          minHeight: isMobile ? "56px" : "64px",
          width: "100%",
          overflowX: "hidden",
          position: "sticky",
          top: "env(safe-area-inset-top, 0px)",
          zIndex: "var(--ue-z-index-nav)",
          transition: prefersReducedMotion ? "none" : undefined,
          animation: prefersReducedMotion ? "none" : undefined,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "flex-start",
            width: "100%",
            padding: isMobile ? "0 10px" : "0 16px",
            boxSizing: "border-box",
            minWidth: 0,
            gap: "0",
          }}
        >
          <Link
            to="/dashboard"
            aria-label={t("navigation:aria.homeLink")}
            className="brand"
            onPointerDown={markScrollFromBottom}
            onClick={(e) => {
              if (isSameTarget("/dashboard")) {
                e.preventDefault()
                scrollToTop(prefersReducedMotion ? "auto" : "smooth")
              }
            }}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: isMobile ? "8px" : "10px",
              minWidth: 0,
              padding: "6px 6px",
              borderRadius: 12,
              textDecoration: "none",
            }}
          >
            <div
              style={{
                width: `${logoWrapSize}px`,
                height: `${logoWrapSize}px`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                borderRadius: "50%",
                background: "#fff",
                boxShadow: "0 0 8px rgba(0,0,0,0.13)",
              }}
            >
              <img
                src={guuLogo}
                alt={t("navigation:brandAlt")}
                width={logoImgSize}
                height={logoImgSize}
                style={{ objectFit: "contain" }}
                loading="eager"
                decoding="async"
              />
            </div>
            <span
              style={{
                color: "#fff",
                fontWeight: 800,
                fontSize: titleFont,
                whiteSpace: "nowrap",
                letterSpacing: ".2px",
              }}
            >
              {t("navigation:brandName")}
            </span>
          </Link>

          {isMobile ? (
            <div style={{ display: "flex", alignItems: "center", marginLeft: "auto", gap: "6px" }}>
              <NotificationsBell />
              {isAuth && user && !loading ? (
                <SmartImage
                  srcRaw={hasAvatar ? avatarSource : avatarFallback}
                  cacheV={hasAvatar ? avatarCacheV : undefined}
                  fallback={avatarFallback}
                  alt={profileAlt}
                  title={profileTitle}
                  style={{
                    width: avatarSize,
                    height: avatarSize,
                    borderRadius: "50%",
                    objectFit: "cover",
                    border: "1px solid #d7d7d7",
                    background: "#fff",
                    cursor: "pointer",
                    display: "block",
                  }}
                  onClick={() => go("/profile")}
                />
              ) : (
                <Skeleton
                  variant="circular"
                  width={avatarSize}
                  height={avatarSize}
                  sx={{ bgcolor: "rgba(255,255,255,0.32)" }}
                  aria-hidden="true"
                />
              )}
              <button
                type="button"
                className="burger-btn"
                style={{
                  background:
                    "linear-gradient(180deg, rgba(255, 255, 255, 0.12), rgba(255, 255, 255, 0.04))",
                  border: "1px solid rgba(255, 255, 255, 0.18)",
                  padding: 0,
                  width: burgerBtnSize,
                  height: burgerBtnSize,
                  minWidth: burgerBtnSize,
                  minHeight: burgerBtnSize,
                  maxWidth: burgerBtnSize,
                  maxHeight: burgerBtnSize,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  cursor: "pointer",
                  color: "rgba(255, 255, 255, 0.92)",
                  borderRadius: 12,
                  flexShrink: 0,
                  boxShadow: "inset 0 1px 0 rgba(255, 255, 255, 0.24)",
                  backdropFilter: "saturate(160%) blur(12px)",
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
                  width="24"
                  height="24"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                  style={{
                    overflow: "visible",
                  }}
                >
                  <line
                    x1="4"
                    y1="8"
                    x2="20"
                    y2="8"
                    style={{
                      transformOrigin: "12px 8px",
                      transform: mobileMenu
                        ? "translateY(4px) rotate(45deg)"
                        : "translateY(0) rotate(0)",
                      transition: "transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
                    }}
                  />
                  <line
                    x1="4"
                    y1="12"
                    x2="20"
                    y2="12"
                    style={{
                      opacity: mobileMenu ? 0 : 1,
                      transition: "opacity 0.2s ease-in-out",
                    }}
                  />
                  <line
                    x1="4"
                    y1="16"
                    x2="20"
                    y2="16"
                    style={{
                      transformOrigin: "12px 16px",
                      transform: mobileMenu
                        ? "translateY(-4px) rotate(-45deg)"
                        : "translateY(0) rotate(0)",
                      transition: "transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
                    }}
                  />
                </svg>
              </button>
            </div>
          ) : (
            <ul
              style={{
                display: "flex",
                flexDirection: "row",
                flexWrap: "wrap",
                alignItems: "center",
                fontWeight: 500,
                listStyle: "none",
                gap: "8px",
                margin: 0,
                padding: 0,
                minWidth: 0,
                marginLeft: "36px",
                flex: 1,
                fontSize: "1.03rem",
              }}
            >
              {menuLinks.map((item) => (
                <li key={item.to}>
                  <Link
                    to={item.to}
                    className={`menu-link${isActive(item.to) ? " active" : ""}`}
                    onPointerDown={markScrollFromBottom}
                    onClick={(e) => {
                      if (isSameTarget(item.to)) {
                        e.preventDefault()
                        scrollToTop(prefersReducedMotion ? "auto" : "smooth")
                      }
                    }}
                  >
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
          )}

          {!isMobile && loading ? (
            <div
              style={{ display: "flex", alignItems: "center", gap: "10px", marginLeft: "8px" }}
              aria-hidden="true"
            >
              <Skeleton
                variant="circular"
                width={36}
                height={36}
                sx={{ bgcolor: "rgba(255,255,255,0.25)" }}
              />
              <Skeleton
                variant="rectangular"
                width={96}
                height={18}
                sx={{ borderRadius: 1, bgcolor: "rgba(255,255,255,0.25)" }}
              />
              <Skeleton
                variant="circular"
                width={32}
                height={32}
                sx={{ bgcolor: "rgba(255,255,255,0.25)" }}
              />
            </div>
          ) : (
            !isMobile &&
            isAuth &&
            user && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "10px",
                  marginLeft: "8px",
                  minWidth: 0,
                  whiteSpace: "nowrap",
                }}
              >
                <NotificationsBell />
                <SmartImage
                  srcRaw={hasAvatar ? avatarSource : avatarFallback}
                  cacheV={hasAvatar ? avatarCacheV : undefined}
                  fallback={avatarFallback}
                  alt={profileAlt}
                  title={profileTitle}
                  style={{
                    width: "36px",
                    height: "36px",
                    borderRadius: "50%",
                    objectFit: "cover",
                    border: "1.5px solid #ccc",
                    background: "#fff",
                    cursor: "pointer",
                    display: "block",
                  }}
                  onClick={() => go("/profile")}
                />
                <button
                  type="button"
                  onClick={() => go("/profile")}
                  aria-label={profileTitle}
                  title={profileTitle}
                  style={{
                    background: "none",
                    border: "none",
                    padding: 0,
                    margin: 0,
                    color: "#fff",
                    fontWeight: 600,
                    whiteSpace: "nowrap",
                    cursor: "pointer",
                    fontSize: rightNameFont,
                    fontFamily: "var(--font-ui)",
                    letterSpacing: "var(--ls-ui)",
                    lineHeight: "var(--lh-ui)",
                  }}
                >
                  {user.full_name}
                </button>
                <button
                  type="button"
                  className="menu-btn-settings"
                  onClick={() => go("/settings")}
                  aria-label={t("navigation:menu.settings")}
                  title={t("navigation:menu.settings")}
                >
                  <svg
                    width="20"
                    height="20"
                    viewBox="0 0 24 24"
                    fill="none"
                    xmlns="http://www.w3.org/2000/svg"
                    aria-hidden="true"
                    focusable="false"
                  >
                    <g stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
                      <path d="M5 7h14" />
                      <path d="M5 12h14" />
                      <path d="M5 17h14" />
                    </g>
                    <circle cx="9" cy="7" r="2" fill="currentColor" />
                    <circle cx="15" cy="12" r="2" fill="currentColor" />
                    <circle cx="11" cy="17" r="2" fill="currentColor" />
                  </svg>
                </button>
              </div>
            )
          )}
        </div>
      </nav>

      {isMobile && (
        <div
          id="mobile-drawer"
          className="mobile-drawer"
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            width: "100vw",
            height: "100vh",
            zIndex: "var(--ue-z-index-overlay)",
            pointerEvents: mobileMenu ? "auto" : "none",
            background: mobileMenu ? "rgba(0,0,0,0.23)" : "transparent",
            transition: prefersReducedMotion ? "none" : "background 0.28s",
            display: "flex",
          }}
          onClick={() => setMobileMenu(false)}
          role="dialog"
          aria-modal="true"
          aria-label={t("navigation:aria.mobileMenu")}
        >
          <nav
            ref={drawerTrapRef}
            className="mobile-drawer-content"
            style={{
              transform: mobileMenu ? "translateX(0)" : "translateX(-120%)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <ul
              style={{
                display: "flex",
                flexDirection: "column",
                listStyle: "none",
                gap: "4px",
                margin: 0,
                padding: 0,
                flex: 1,
                width: "100%",
                overflowY: "auto",
              }}
            >
              {menuLinks.map((item) => (
                <li key={item.to} style={{ width: "100%" }}>
                  <Link
                    to={item.to}
                    onClick={() => setMobileMenu(false)}
                    className={`menu-link${isSamePath(item.to) ? " active" : ""}`}
                    style={{ width: "100%" }}
                  >
                    {item.label}
                  </Link>
                </li>
              ))}
              {isAuth && user && (
                <li style={{ width: "100%", marginTop: "4px" }}>
                  <button
                    type="button"
                    className="menu-link"
                    onClick={(e) => {
                      e.stopPropagation()
                      setMobileMenu(false)
                      go("/settings")
                    }}
                    style={{
                      width: "100%",
                      justifyContent: "flex-start",
                      padding: "10px 14px",
                      borderRadius: "10px",
                      height: "auto",
                      background: "transparent",
                      border: "1px solid transparent",
                      boxShadow: "none",
                      backdropFilter: "none",
                      cursor: "pointer",
                      fontSize: "16px",
                    }}
                    aria-label={t("navigation:menu.settings")}
                  >
                    {t("navigation:menu.settings")}
                  </button>
                </li>
              )}
            </ul>

            <div
              style={{
                padding: "24px 0",
                width: "100%",
                borderTop: "1px solid rgba(255,255,255,0.08)",
              }}
            >
              <div
                style={{ fontSize: "12px", color: "rgba(255,255,255,0.4)", textAlign: "center" }}
              >
                © {new Date().getFullYear()} {t("navigation:brandName")}
              </div>
            </div>
          </nav>
        </div>
      )}
    </>
  )
}

export default Navbar
