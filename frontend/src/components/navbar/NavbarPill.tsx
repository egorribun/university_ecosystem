import { cn } from "@/utils/cn"

interface NavbarPillProps {
  isCompact: boolean
  prefersReducedMotion: boolean
  children: React.ReactNode
}

/**
 * NavbarPill — morphing inner container (Wave 51: premium glass).
 *
 * The parent <nav> has FIXED height (64px always, no layout shift).
 * This container fills that height and transitions visual properties:
 * - Expanded: full width, no border-radius, transparent bg
 * - Compact: bounded matte surface with a restrained gradient accent
 *
 * Premium features (compact only):
 * - No continuous or layout-triggering animation
 * - ::after gradient overlay for directional lighting (lighter top edge)
 * - glass-noise texture for frosted glass feel
 * - 6s breathing animation (slower, more organic)
 */
export function NavbarPill({ isCompact, prefersReducedMotion, children }: NavbarPillProps) {
  const dur = prefersReducedMotion ? "duration-0" : "duration-500"
  const ease = "ease-[var(--ease-premium)]"

  return (
    <div
      className={cn(
        "flex w-full items-center box-border",
        "transition-[transform,opacity]",
        dur,
        ease,
        isCompact
          ? [
              // Compact matte surface; layout properties snap at the hysteresis boundary.
              "relative mx-auto h-(--navbar-pill-h)",
              "max-w-(--navbar-pill-max-w) rounded-[var(--navbar-pill-radius)]",
              "bg-(--pill-bg) border border-(--pill-border)",
              "px-(--navbar-pill-px)",
            ]
          : [
              // Expanded: full width, full height, no decoration
              "h-full max-w-none rounded-none",
              "bg-transparent border border-transparent shadow-none",
              "px-fluid-x",
            ]
      )}
    >
      {/* Directional gradient overlay — top-edge light reflection */}
      {isCompact && (
        <div
          className="pointer-events-none absolute inset-0 rounded-[inherit] z-0"
          style={{ background: "var(--pill-gradient)" }}
          aria-hidden="true"
        />
      )}
      {/* Content sits above the gradient overlay */}
      <div className={cn("relative z-[1] flex w-full items-center", isCompact ? "gap-0" : "")}>
        {children}
      </div>
    </div>
  )
}
