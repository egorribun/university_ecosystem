import { Link, useRouterState } from "@tanstack/react-router"
import { useMemo, useRef } from "react"
import { useIsomorphicLayoutEffect } from "@/hooks/useIsomorphicLayoutEffect"
import {
  LayoutDashboard as DashboardIcon,
  Newspaper as ArticleIcon,
  Calendar as EventNoteIcon,
  CalendarDays as TodayIcon,
  User as PersonIcon,
} from "lucide-react"
import { useTranslation } from "react-i18next"
import { m, AnimatePresence } from "framer-motion"
import { springSoft } from "@/utils/animations"
import useMediaQuery from "@/hooks/useMediaQuery"
import { markIfFromBottom, smoothToTop, getScrollRoot } from "@/utils/scrollUtils"
import { useSlidingIndicator } from "@/hooks/ui/useSlidingIndicator"

function samePath(a: string, b: string) {
  const na = a.replace(/\/+$/, "")
  const nb = b.replace(/\/+$/, "")
  return na === nb
}

export default function MobileBottomNav() {
  const pathname = useRouterState({ select: (s) => s.location.pathname })
  const { t } = useTranslation(["navigation"])
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")

  // Wave 128 SW3 — useIsomorphicLayoutEffect picks useEffect on SSR
  // (avoids React's "useLayoutEffect does nothing on the server" warning
  // surfaced by W128 plan exploration code-explorer audit). Behavior
  // identical on client.
  useIsomorphicLayoutEffect(() => {
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

  // Wave 124 SW1 — replaces framer-motion layoutId="bottom-nav-pill" (requires
  // domMax). Single absolutely-positioned pill slides between active items via
  // CSS transform transition. Computes target rect via useSlidingIndicator.
  const activeNavTo = useMemo(() => {
    for (const it of items) {
      const isActive = pathname.startsWith(it.to)
      if (isActive) return it.to
    }
    return null
  }, [items, pathname])
  const navRef = useRef<HTMLElement>(null)
  const pillRect = useSlidingIndicator(navRef, activeNavTo)

  if (hidden) return null

  return (
    <>
      <nav
        ref={navRef}
        className="fixed bottom-0 left-0 right-0 z-(--z-navbar) flex h-(--bottom-nav-h) w-full items-center justify-around bottom-nav-glass border-t border-glass-border pb-(--safe-area-bottom) shadow-up transition-all md:hidden"
        role="navigation"
        aria-label={t("navigation:aria.mainNavigation")}
      >
        {pillRect && (
          <span
            aria-hidden="true"
            className="absolute rounded-(--bottom-nav-pill-radius) bottom-nav-pill z-negative"
            style={{
              transform: `translate3d(${pillRect.left + 8}px, ${pillRect.top + 4}px, 0)`,
              width: pillRect.width - 16,
              height: pillRect.height - 8,
              transition: prefersReducedMotion
                ? "none"
                : "transform 280ms cubic-bezier(0.34, 1.3, 0.64, 1), width 280ms cubic-bezier(0.34, 1.3, 0.64, 1), height 280ms cubic-bezier(0.34, 1.3, 0.64, 1)",
            }}
          />
        )}
        {items.map((it) => {
          const isActive = pathname.startsWith(it.to)
          const Icon = it.icon
          return (
            <Link
              key={it.to}
              to={it.to}
              data-tab-key={it.to}
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
              <div className="relative z-surface">
                <m.span
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
                </m.span>
              </div>

              {/* Label — spring scale entry for premium feel */}
              <AnimatePresence mode="wait">
                {isActive && (
                  <m.span
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
                  </m.span>
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
