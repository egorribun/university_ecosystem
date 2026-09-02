import { Link } from "@tanstack/react-router"
import { cn } from "@/utils/cn"
import { type NavigationItem } from "@/config/navigation"
import { type ScrollBehavior } from "@/hooks/useScrollRestoration"

interface DesktopNavProps {
  menuLinks: NavigationItem[]
  isActive: (to: string) => boolean
  isSameTarget: (to: string) => boolean
  scrollToTop: (behavior?: ScrollBehavior) => void
  markScrollFromBottom: () => void
  prefersReducedMotion: boolean
  isCompact: boolean
}

export const DesktopNav = ({
  menuLinks,
  isActive,
  isSameTarget,
  scrollToTop,
  markScrollFromBottom,
  prefersReducedMotion,
  isCompact,
}: DesktopNavProps) => {
  return (
    <ul
      className={cn(
        "navbar-desktop-nav flex flex-row items-center m-0 p-0 min-w-0 list-none",
        isCompact ? "ml-(--space-4) gap-0.5" : "ml-(--space-8) gap-1"
      )}
    >
      {menuLinks.map((item) => {
        const Icon = item.icon
        const active = isActive(item.to)
        return (
          <li key={item.to}>
            <Link
              id={`navbar-link-${item.to.replace(/\//g, "") || "home"}`}
              to={item.to}
              className="nav-link-premium"
              data-active={active || undefined}
              onPointerDown={markScrollFromBottom}
              onClick={(e) => {
                if (isSameTarget(item.to)) {
                  e.preventDefault()
                  scrollToTop(prefersReducedMotion ? "auto" : "smooth")
                }
              }}
            >
              {/* Icon — instant swap, no crossfade (prevents flash during pill morph) */}
              <span
                className={cn(
                  "flex items-center justify-center",
                  isCompact
                    ? "relative opacity-100"
                    : "absolute inset-0 opacity-0 pointer-events-none"
                )}
              >
                <Icon size={18} aria-hidden="true" />
              </span>

              {/* Text — instant swap */}
              <span
                className={cn(
                  "whitespace-nowrap",
                  isCompact
                    ? "absolute inset-0 flex items-center justify-center opacity-0 pointer-events-none"
                    : "relative opacity-100"
                )}
              >
                {item.label}
              </span>
            </Link>
          </li>
        )
      })}
    </ul>
  )
}
