import { Link, useRouterState } from "@tanstack/react-router"
import { useLayoutEffect, useMemo } from "react"
import {
  LayoutDashboard as DashboardIcon,
  Newspaper as ArticleIcon,
  Calendar as EventNoteIcon,
  CalendarDays as TodayIcon,
  User as PersonIcon,
} from "lucide-react"
import { useTranslation } from "react-i18next"
import { motion } from "framer-motion"
import { springBouncy, springSoft } from "@/utils/animations"

import { markIfFromBottom, smoothToTop, getScrollRoot } from "@/utils/scrollUtils"

function samePath(a: string, b: string) {
  const na = a.replace(/\/+$/, "") || "/"
  const nb = b.replace(/\/+$/, "") || "/"
  return na === nb
}

export default function MobileBottomNav() {
  const pathname = useRouterState({ select: (s) => s.location.pathname })
  const { t } = useTranslation(["navigation"])

  useLayoutEffect(() => {
    if (sessionStorage.getItem("__scrollTopNext") === "1") {
      sessionStorage.removeItem("__scrollTopNext")
      requestAnimationFrame(() => smoothToTop(getScrollRoot()))
    }
  }, [pathname])

  const items = useMemo(
    () => [
      {
        to: "/dashboard",
        label: t("navigation:menu.dashboard"),
        icon: <DashboardIcon size={22} />,
      },
      { to: "/news", label: t("navigation:menu.news"), icon: <ArticleIcon size={22} /> },
      { to: "/events", label: t("navigation:menu.events"), icon: <EventNoteIcon size={22} /> },
      { to: "/schedule", label: t("navigation:menu.schedule"), icon: <TodayIcon size={22} /> },
      { to: "/profile", label: t("navigation:menu.profile"), icon: <PersonIcon size={22} /> },
    ],
    [t]
  )

  const hideOn = ["/login", "/register", "/forgot-password", "/reset-password"]
  const hidden = hideOn.some((p) => pathname.startsWith(p))
  if (hidden) return null

  return (
    <>
      <nav
        className="fixed bottom-0 left-0 right-0 z-navbar flex h-navbar-height w-full items-center justify-around border-t border-glass-border bg-nav backdrop-blur-nav pb-(--safe-area-bottom) shadow-premium transition-all md:hidden"
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
            <Link
              key={it.to}
              to={it.to}
              onPointerDown={markIfFromBottom}
              onClick={(e) => {
                if (samePath(pathname, it.to)) {
                  e.preventDefault()
                  smoothToTop(getScrollRoot())
                }
              }}
              className={
                "group relative flex flex-1 flex-col items-center justify-center gap-(--space-2) py-(--space-1) text-text-primary transition-all outline-none select-none " +
                (isActive
                  ? "active text-brand font-bold scale-110"
                  : "opacity-strong hover:opacity-100")
              }
              aria-label={it.label}
            >
              <div className="relative">
                {isActive && (
                  <motion.div
                    layoutId="bottom-nav-active-glow"
                    className="absolute inset-(calc(var(--space-4)*-1)) rounded-full bg-brand opacity-subtle blur-glass z-negative"
                    transition={springBouncy}
                  />
                )}
                <motion.span
                  className="block z-decor"
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
                className="z-decor text-label-xs font-black uppercase tracking-tight"
                animate={{
                  opacity: isActive ? 1 : 0.7,
                }}
                transition={springSoft}
              >
                {it.label}
              </motion.span>
            </Link>
          )
        })}
      </nav>
      {/* Spacer for bottom nav */}
      {!pathname.startsWith("/messenger") && (
        <span
          className="h-navbar-height bg-transparent transition-colors duration-slow md:hidden relative z-decor"
          aria-hidden="true"
        />
      )}
    </>
  )
}
