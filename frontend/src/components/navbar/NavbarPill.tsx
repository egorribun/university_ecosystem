import { cn } from "@/utils/cn"

interface NavbarPillProps {
  isCompact: boolean
  prefersReducedMotion: boolean
  children: React.ReactNode
}

/**
 * NavbarPill — morphing inner container.
 *
 * The parent <nav> has FIXED height (64px always, no layout shift).
 * This container fills that height and transitions visual properties:
 * - Expanded: full width, no border-radius, transparent bg
 * - Compact: max-width 780px, pill shape, glass bg, margin to shrink inside nav
 *
 * Uses `my-auto` + fixed pill height so it floats centered inside the 64px nav.
 */
export function NavbarPill({ isCompact, prefersReducedMotion, children }: NavbarPillProps) {
  const dur = prefersReducedMotion ? "duration-0" : "duration-500"
  const ease = "ease-[var(--ease-premium)]"

  return (
    <div
      className={cn(
        "flex w-full items-center box-border",
        "transition-[max-width,height,border-radius,background,border-color,box-shadow,backdrop-filter,padding,margin]",
        dur, ease,
        isCompact
          ? [
              // Compact pill: centered, rounded, glass bg, shorter
              "mx-auto h-(--navbar-pill-h)",
              "max-w-(--navbar-pill-max-w) rounded-[var(--navbar-pill-radius)]",
              "bg-(--pill-bg) border border-(--pill-border) shadow-[var(--pill-shadow)]",
              "backdrop-blur-xl backdrop-saturate-[1.4]",
              "px-(--navbar-pill-px)",
              !prefersReducedMotion && "animate-pill-breathe",
            ]
          : [
              // Expanded: full width, full height, no decoration
              "h-full max-w-none rounded-none",
              "bg-transparent border border-transparent shadow-none",
              "px-fluid-x",
            ]
      )}
    >
      {children}
    </div>
  )
}
