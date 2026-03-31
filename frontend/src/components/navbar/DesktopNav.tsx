import { Link } from "@tanstack/react-router"
import { motion } from "framer-motion"
import { cn } from "@/utils/cn"
import { springSoft } from "@/utils/animations"
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

/**
 * DesktopNav — crossfade between text labels and icons.
 *
 * Layout strategy:
 * - Expanded: text is in-flow (determines width), icon is absolute (hidden)
 * - Compact:  icon is in-flow (determines width), text is absolute (hidden)
 *
 * Only `opacity` animates (GPU composited, zero reflow).
 * The in-flow/absolute swap is instant (not animated) — it happens at
 * the same moment as the opacity crossfade, so it's invisible.
 */
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
        "flex flex-row items-center m-0 p-0 min-w-0 list-none font-medium",
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
              className={cn(
                "relative flex items-center justify-center rounded-xl no-underline",
                "transition-[padding,color,background]",
                prefersReducedMotion ? "duration-0" : "duration-200",
                isCompact ? "px-2 py-2" : "px-3.5 py-2",
                active
                  ? "text-(--nav-active-color) font-semibold"
                  : [
                      "text-(--text-secondary)",
                      "hover:text-(--text-primary) hover:bg-(--bg-surface-hover)/(--opacity-soft)",
                      !prefersReducedMotion && "hover:-translate-y-px active:scale-[0.98]",
                    ]
              )}
              onPointerDown={markScrollFromBottom}
              onClick={(e) => {
                if (isSameTarget(item.to)) {
                  e.preventDefault()
                  scrollToTop(prefersReducedMotion ? "auto" : "smooth")
                }
              }}
            >
              {/* Icon: instant swap — no crossfade, no "double exposure" */}
              <span
                className={cn(
                  "flex items-center justify-center",
                  isCompact
                    ? "relative opacity-100"
                    : "absolute inset-0 opacity-0 pointer-events-none"
                )}
              >
                <Icon
                  className={active ? "text-(--nav-active-color)" : "text-(--text-secondary)"}
                  size={18}
                  aria-hidden="true"
                />
              </span>

              {/* Text: instant swap — content changes immediately, pill morphs smoothly */}
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

              {/* Active indicator */}
              {active && (
                <motion.div
                  layoutId="navbar-active-bar"
                  className={cn(
                    "absolute",
                    isCompact
                      ? "bottom-0 left-1/2 -translate-x-1/2 h-[5px] w-[5px] rounded-full bg-(--nav-active-color)"
                      : "bottom-0 inset-x-3 h-0.5 rounded-full bg-(--nav-active-color)"
                  )}
                  style={{ boxShadow: "0 0 8px var(--nav-active-glow)" }}
                  transition={prefersReducedMotion ? { duration: 0 } : springSoft}
                />
              )}
            </Link>
          </li>
        )
      })}
    </ul>
  )
}
