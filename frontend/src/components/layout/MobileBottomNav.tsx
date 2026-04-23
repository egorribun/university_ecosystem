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
import { motion, AnimatePresence } from "framer-motion"
import { springBouncy, springSoft } from "@/utils/animations"
import useMediaQuery from "@/hooks/useMediaQuery"
import { markIfFromBottom, smoothToTop, getScrollRoot } from "@/utils/scrollUtils"

function samePath(a: string, b: string) {
  const na = a.replace(/\/+$/, "") || "/"
  const nb = b.replace(/\/+$/, "") || "/"
  return na === nb
}

export default function MobileBottomNav() {
  const pathname = useRouterState({ select: (s) => s.location.pathname })
  const { t } = useTranslation(["navigation"])
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")

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
        icon: DashboardIcon,
      },
      { to: "/news", label: t("navigation:menu.news"), icon: ArticleIcon },
      { to: "/events", label: t("navigation:menu.events"), icon: EventNoteIcon },
      { to: "/schedule", label: t("navigation:menu.schedule"), icon: TodayIcon },
      { to: "/profile", label: t("navigation:menu.profile"), icon: PersonIcon },
    ],
    [t]
  )

  const hideOn = ["/login", "/register", "/forgot-password", "/reset-password"]
  const hidden = hideOn.some((p) => pathname.startsWith(p))
  if (hidden) return null

  return (
    <>
      <nav
        className="fixed bottom-0 left-0 right-0 z-(--z-navbar) flex h-(--bottom-nav-h) w-full items-center justify-around bottom-nav-glass border-t border-glass-border pb-(--safe-area-bottom) shadow-up transition-all md:hidden"
        role="navigation"
        aria-label={t("navigation:aria.mainNavigation")}
      >
        {items.map((it) => {
          const isActive = pathname.startsWith(it.to) && (it.to !== "/" || pathname === "/")
          const Icon = it.icon
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
              className="group relative flex flex-1 flex-col items-center justify-center py-1 text-text-primary transition-all outline-none select-none"
              aria-label={it.label}
            >
              {/* Morphing pill indicator */}
              {isActive && (
                <motion.div
                  layoutId="bottom-nav-pill"
                  className="absolute inset-x-2 top-1 bottom-1 rounded-(--bottom-nav-pill-radius) bottom-nav-pill z-negative"
                  transition={prefersReducedMotion ? { duration: 0 } : springBouncy}
                />
              )}

              <div className="relative z-surface">
                <motion.span
                  className="block"
                  animate={{
                    y: isActive ? -1 : 0,
                    scale: isActive ? 1.1 : 1,
                  }}
                  whileTap={prefersReducedMotion ? undefined : { scale: 0.9 }}
                  transition={prefersReducedMotion ? { duration: 0 } : springSoft}
                >
                  {/* Active icon gets colored circular background */}
                  {isActive ? (
                    <span
                      className="flex items-center justify-center rounded-lg p-0.5"
                      style={{ backgroundColor: "var(--nav-active-glow)" }}
                    >
                      <Icon size={20} className="text-(--nav-active-color)" />
                    </span>
                  ) : (
                    <Icon
                      size={20}
                      className="text-(--text-secondary) group-hover:text-(--text-primary)"
                    />
                  )}
                </motion.span>
              </div>

              {/* Label — spring scale entry for premium feel */}
              <AnimatePresence mode="wait">
                {isActive && (
                  <motion.span
                    key={`label-${it.to}`}
                    initial={prefersReducedMotion ? false : { opacity: 0, height: 0, scale: 0.8 }}
                    animate={{ opacity: 1, height: "auto", scale: 1 }}
                    exit={{ opacity: 0, height: 0, scale: 0.8 }}
                    transition={
                      prefersReducedMotion
                        ? { duration: 0 }
                        : { duration: 0.2, ease: [0.16, 1, 0.3, 1] }
                    }
                    className="z-surface text-[10px] font-bold uppercase tracking-tight text-(--nav-active-color) mt-0.5 leading-tight"
                  >
                    {it.label}
                  </motion.span>
                )}
              </AnimatePresence>

              {/* Dot for inactive items — slightly larger for visibility */}
              {!isActive && (
                <span className="h-1 w-1.5 rounded-full bg-(--text-tertiary) mt-1.5 opacity-0 group-hover:opacity-100 transition-opacity duration-200" />
              )}
            </Link>
          )
        })}
      </nav>

      {/* Spacer for bottom nav */}
      {!pathname.startsWith("/messenger") && (
        <span
          className="h-(--bottom-nav-h) bg-transparent md:hidden relative z-decor"
          aria-hidden="true"
        />
      )}
    </>
  )
}
