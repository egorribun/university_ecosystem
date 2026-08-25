import { Link, useRouterState } from "@tanstack/react-router"
import { useEffect, useMemo, useRef, useState } from "react"
import { useIsomorphicLayoutEffect } from "@/hooks/useIsomorphicLayoutEffect"
import {
  LayoutDashboard as DashboardIcon,
  Newspaper as ArticleIcon,
  Calendar as EventNoteIcon,
  CalendarDays as TodayIcon,
  User as PersonIcon,
} from "lucide-react"
import { useTranslation } from "react-i18next"
import { markIfFromBottom, smoothToTop, getScrollRoot } from "@/utils/scrollUtils"
import useMediaQuery from "@/hooks/useMediaQuery"

function samePath(a: string, b: string) {
  const na = a.replace(/\/+$/, "")
  const nb = b.replace(/\/+$/, "")
  return na === nb
}

function isSectionActive(pathname: string, section: string) {
  const path = pathname.replace(/\/+$/, "")
  const target = section.replace(/\/+$/, "")
  return path === target || path.startsWith(`${target}/`)
}

export default function MobileBottomNav() {
  const pathname = useRouterState({ select: (s) => s.location.pathname })
  const { t } = useTranslation(["navigation"])
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")
  const deferredScrollFrame = useRef<number | null>(null)
  const [isVirtualKeyboardOpen, setIsVirtualKeyboardOpen] = useState(false)

  // Wave 128 SW3 — useIsomorphicLayoutEffect picks useEffect on SSR
  // (avoids React's "useLayoutEffect does nothing on the server" warning
  // surfaced by W128 plan exploration code-explorer audit). Behavior
  // identical on client.
  useIsomorphicLayoutEffect(() => {
    if (sessionStorage.getItem("__scrollTopNext") === "1") {
      sessionStorage.removeItem("__scrollTopNext")
      deferredScrollFrame.current = requestAnimationFrame(() => {
        deferredScrollFrame.current = null
        smoothToTop(getScrollRoot(), prefersReducedMotion ? "auto" : "smooth")
      })
    }

    return () => {
      if (deferredScrollFrame.current !== null) {
        cancelAnimationFrame(deferredScrollFrame.current)
        deferredScrollFrame.current = null
      }
    }
  }, [pathname, prefersReducedMotion])

  useEffect(() => {
    const viewport = window.visualViewport
    if (!viewport) return

    const syncKeyboardState = () => {
      const activeElement = document.activeElement
      const hasEditableFocus =
        activeElement instanceof HTMLInputElement ||
        activeElement instanceof HTMLTextAreaElement ||
        (activeElement instanceof HTMLElement && activeElement.isContentEditable)
      const atDefaultScale = viewport.scale === undefined || Math.abs(viewport.scale - 1) < 0.01
      setIsVirtualKeyboardOpen(
        hasEditableFocus && atDefaultScale && window.innerHeight - viewport.height > 150
      )
    }
    syncKeyboardState()
    viewport.addEventListener("resize", syncKeyboardState)
    viewport.addEventListener("scroll", syncKeyboardState)
    return () => {
      viewport.removeEventListener("resize", syncKeyboardState)
      viewport.removeEventListener("scroll", syncKeyboardState)
    }
  }, [])

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
  const hidden = hideOn.some((path) => isSectionActive(pathname, path))

  const activeIndex = items.findIndex((item) => isSectionActive(pathname, item.to))

  if (hidden) return null

  return (
    <>
      <nav
        className={`fixed inset-x-0 bottom-0 z-(--z-navbar) grid h-[calc(var(--bottom-nav-h)+var(--safe-area-bottom))] w-full grid-cols-5 items-stretch border-t border-glass-border bottom-nav-glass pb-(--safe-area-bottom) shadow-up transition-[transform,opacity] duration-200 motion-reduce:transition-none md:hidden ${isVirtualKeyboardOpen ? "pointer-events-none translate-y-full opacity-0" : "translate-y-0 opacity-100"}`}
        role="navigation"
        aria-label={t("navigation:aria.mainNavigation")}
        aria-hidden={isVirtualKeyboardOpen || undefined}
        data-virtual-keyboard={isVirtualKeyboardOpen ? "open" : "closed"}
        inert={isVirtualKeyboardOpen || undefined}
      >
        {activeIndex >= 0 && (
          <span
            aria-hidden="true"
            data-nav-indicator
            className="pointer-events-none absolute left-0 top-0 h-(--bottom-nav-h) w-1/5 p-1.5 transition-[transform,opacity] duration-300 motion-reduce:transition-none"
            style={{
              transform: `translate3d(${activeIndex * 100}%, 0, 0)`,
            }}
          >
            <span className="block h-full w-full rounded-(--bottom-nav-pill-radius) border border-(--bottom-pill-border) bg-(--bottom-pill-bg)" />
          </span>
        )}
        {items.map((it) => {
          const isActive = isSectionActive(pathname, it.to)
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
                  smoothToTop(getScrollRoot(), prefersReducedMotion ? "auto" : "smooth")
                }
              }}
              className="group relative flex h-full min-h-11 w-full flex-col items-center justify-center text-text-primary outline-none select-none focus-visible:shadow-focus"
              aria-label={it.label}
              aria-current={isActive ? "page" : undefined}
            >
              <span
                data-nav-icon
                aria-hidden="true"
                className={`relative z-surface flex h-6 w-6 shrink-0 items-center justify-center rounded-lg transition-[transform,color] duration-200 motion-reduce:transition-none ${isActive ? "-translate-y-px text-(--nav-active-color)" : "translate-y-0 text-(--text-secondary) group-hover:text-(--text-primary)"}`}
              >
                <Icon size={20} aria-hidden="true" />
              </span>
              <span
                data-nav-label
                aria-hidden="true"
                className={`relative z-surface mt-0.5 h-3 text-[10px] font-bold uppercase leading-3 tracking-tight text-(--nav-active-color) transition-opacity duration-200 motion-reduce:transition-none ${isActive ? "opacity-100" : "opacity-0"}`}
              >
                {it.label}
              </span>
            </Link>
          )
        })}
      </nav>

      {/* Spacer for bottom nav */}
      {!isVirtualKeyboardOpen && !isSectionActive(pathname, "/messenger") && (
        <span
          data-bottom-nav-spacer
          className="relative z-decor block h-[calc(var(--bottom-nav-h)+var(--safe-area-bottom))] bg-transparent md:hidden"
          aria-hidden="true"
        />
      )}
    </>
  )
}
