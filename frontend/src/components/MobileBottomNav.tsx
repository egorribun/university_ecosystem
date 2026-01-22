import { NavLink, useLocation } from "react-router-dom"
import { useLayoutEffect, useMemo } from "react"
import DashboardIcon from "@mui/icons-material/Dashboard"
import ArticleIcon from "@mui/icons-material/Article"
import EventNoteIcon from "@mui/icons-material/EventNote"
import TodayIcon from "@mui/icons-material/Today"
import PersonIcon from "@mui/icons-material/Person"
import { useTranslation } from "react-i18next"
import { motion } from "framer-motion"
import { springBouncy, springSoft, hoverScale } from "@/utils/animations"

function getScrollRoot(): HTMLElement {
  const cands: (Element | null | Document | HTMLElement)[] = [
    document.querySelector("[data-scroll-root]"),
    document.querySelector("main[role='main']"),
    document.querySelector("main"),
    document.getElementById("scroll-root"),
    document.querySelector("#root"),
    (document as any).scrollingElement,
    document.documentElement,
    document.body,
  ]
  for (const el of cands) {
    if (!el) continue
    const e = el as HTMLElement
    const oy = getComputedStyle(e).overflowY
    const scrollable = (oy === "auto" || oy === "scroll") && e.scrollHeight > e.clientHeight
    if (scrollable) return e
  }
  return (document.scrollingElement || document.documentElement) as HTMLElement
}

function smoothToTop(target: HTMLElement) {
  try {
    ;(target as any).scrollTo({ top: 0, behavior: "smooth" })
  } catch {
    const start = target.scrollTop
    const duration = 420
    let t0 = 0
    const step = (ts: number) => {
      if (!t0) t0 = ts
      const p = Math.min(1, (ts - t0) / duration)
      const eased = 1 - Math.pow(1 - p, 3)
      target.scrollTop = Math.round(start * (1 - eased))
      if (p < 1) requestAnimationFrame(step)
    }
    requestAnimationFrame(step)
  }
}

function markIfFromBottom() {
  const el = getScrollRoot()
  const threshold = 24
  const nearBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - threshold
  if (nearBottom) sessionStorage.setItem("__scrollTopNext", "1")
}

function samePath(a: string, b: string) {
  const na = a.replace(/\/+$/, "") || "/"
  const nb = b.replace(/\/+$/, "") || "/"
  return na === nb
}

export default function MobileBottomNav() {
  const { pathname } = useLocation()
  const { t } = useTranslation(["navigation"])

  useLayoutEffect(() => {
    if (sessionStorage.getItem("__scrollTopNext") === "1") {
      sessionStorage.removeItem("__scrollTopNext")
      const el = getScrollRoot()
      requestAnimationFrame(() => requestAnimationFrame(() => smoothToTop(el)))
    }
  }, [pathname])

  const items = useMemo(
    () => [
      { to: "/dashboard", label: t("navigation:menu.dashboard"), icon: <DashboardIcon /> },
      { to: "/news", label: t("navigation:menu.news"), icon: <ArticleIcon /> },
      { to: "/events", label: t("navigation:menu.events"), icon: <EventNoteIcon /> },
      { to: "/schedule", label: t("navigation:menu.schedule"), icon: <TodayIcon /> },
      { to: "/profile", label: t("navigation:menu.profile"), icon: <PersonIcon /> },
    ],
    [t]
  )

  const hideOn = ["/login", "/register", "/forgot-password", "/reset-password"]
  const hidden = hideOn.some((p) => pathname.startsWith(p))
  if (hidden) return null

  return (
    <>
      <nav
        className="fixed bottom-0 left-0 right-0 z-50 flex h-[calc(4rem+env(safe-area-inset-bottom))] w-full items-center justify-around border-t border-[var(--glass-border)] bg-[var(--nav-bg)] backdrop-blur-[var(--glass-blur)] pb-[env(safe-area-inset-bottom)] shadow-[var(--shadow-up)] transition-all md:hidden"
        style={{
          transitionDuration: "600ms",
          transitionTimingFunction: "var(--ease-premium)",
        }}
        role="navigation"
        aria-label={t("navigation:aria.mainNavigation")}
      >
        {items.map((it) => {
          const isActive = pathname.startsWith(it.to) && (it.to !== "/" || pathname === "/")
          return (
            <NavLink
              key={it.to}
              to={it.to}
              onPointerDown={markIfFromBottom}
              onClick={(e) => {
                if (samePath(pathname, it.to)) {
                  e.preventDefault()
                  const el = getScrollRoot()
                  requestAnimationFrame(() => smoothToTop(el))
                }
              }}
              className={({ isActive }) =>
                "group relative flex flex-1 flex-col items-center justify-center gap-1.5 py-1 text-[var(--nav-text)] transition-all outline-none select-none " +
                (isActive
                  ? "active text-[var(--nav-link)] font-bold scale-110"
                  : "opacity-60 hover:opacity-100")
              }
              aria-label={it.label}
            >
              <div className="relative">
                {isActive && (
                  <motion.div
                    layoutId="bottom-nav-active-glow"
                    className="absolute inset-[-14px] rounded-full bg-[var(--nav-link)] opacity-10 blur-xl -z-10"
                    transition={springBouncy}
                  />
                )}
                <motion.span
                  className="block z-10"
                  animate={{
                    y: isActive ? -2 : 0,
                    scale: isActive ? 1.15 : 1,
                  }}
                  whileTap={{ scale: 0.9 }}
                  transition={springSoft}
                >
                  {it.icon}
                </motion.span>
              </div>
              <motion.span
                className="z-10 text-[9px] font-bold uppercase tracking-tighter"
                animate={{
                  opacity: isActive ? 1 : 0.6,
                }}
                transition={springSoft}
              >
                {it.label}
              </motion.span>
            </NavLink>
          )
        })}
      </nav>
      {/* Spacer for bottom nav */}
      {!pathname.startsWith("/messenger") && (
        <div
          className="h-[calc(4rem+env(safe-area-inset-bottom))] bg-[var(--page-bg)] transition-colors duration-500 md:hidden"
          aria-hidden="true"
        />
      )}
    </>
  )
}
