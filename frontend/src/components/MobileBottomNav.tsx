import { NavLink, useLocation } from "react-router-dom"
import { useLayoutEffect, useMemo } from "react"
import DashboardIcon from "@mui/icons-material/Dashboard"
import ArticleIcon from "@mui/icons-material/Article"
import EventNoteIcon from "@mui/icons-material/EventNote"
import TodayIcon from "@mui/icons-material/Today"
import PersonIcon from "@mui/icons-material/Person"
import { useTranslation } from "react-i18next"
import { motion } from "framer-motion"

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
        className="bottom-nav glass"
        role="navigation"
        aria-label={t("navigation:aria.mainNavigation")}
      >
        {items.map((it) => {
          const isActive = pathname.startsWith(it.to) && (it.to !== "/" || pathname === "/")
          // Special case for dashboard/news exact vs prefix matching if needed,
          // but specifically for bottom nav usually "startsWith" is good for sections,
          // except maybe dashboard if it's root.
          // However, the original code relied on NavLink's fuzzy matching or expected exact paths.
          // Let's rely on useLocation pathname comparison for the active pill to be totally controlled.

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
            onKeyDown={(e) => {
              if ((e.key === "Enter" || e.key === " ") && samePath(pathname, it.to)) {
                e.preventDefault()
                const el = getScrollRoot()
                requestAnimationFrame(() => smoothToTop(el))
              }
            }}
            className={({ isActive }) => "bottom-nav__item relative" + (isActive ? " active" : "")}
            aria-label={it.label}
          >
            {isActive && (
              <motion.div
                layoutId="bottom-nav-active-pill"
                className="absolute inset-0 rounded-xl bg-[color:color-mix(in_srgb,var(--nav-link)_12%,transparent)] dark:bg-[color:color-mix(in_srgb,var(--nav-link)_20%,transparent)]"
                transition={{ type: "spring", stiffness: 300, damping: 30 }}
              />
            )}
            <span className="bottom-nav__icon z-10">{it.icon}</span>
            <span className="bottom-nav__label z-10">{it.label}</span>
          </NavLink>
        )})}
      </nav>
      {!pathname.startsWith("/messenger") && (
        <div className="bottom-nav-spacer" aria-hidden="true" />
      )}
    </>
  )
}
