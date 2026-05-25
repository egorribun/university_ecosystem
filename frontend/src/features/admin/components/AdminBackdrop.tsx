type AdminBackdropProps = {
  isNarrow: boolean
  prefersReducedMotion: boolean
}

/**
 * AdminBackdrop — decorative orbs for /admin routes.
 *
 * Per W118 SW3 CLS-118-03 lesson: orbs use **pixel-based** heights + fixed
 * pixel offsets. Percentage-based heights/positions relative to the absolute
 * content container shift dramatically as content grows (admin pages can
 * scroll long: AdminNotifications has dead-letter rows, AdminAudit has
 * paginated logs). Pixel sizing keeps CLS stable.
 *
 * Pattern mirrors ActivityBackdrop.tsx (Wave 84) — 4 orbs, conditional
 * drifting conic suppressed under reduced-motion, aria-hidden +
 * pointer-events-none + position: absolute -z-1 discipline.
 */
export function AdminBackdrop({ isNarrow, prefersReducedMotion }: AdminBackdropProps) {
  return (
    <div className="pointer-events-none absolute inset-0 -z-1 overflow-hidden" aria-hidden="true">
      {/* Primary hero orb — top center (indigo glow) */}
      <div
        className="absolute -top-20 left-1/2 h-[500px] w-[800px] max-w-full -translate-x-1/2"
        style={{
          background: "radial-gradient(ellipse at 50% 0%, var(--admin-hero-orb), transparent 72%)",
          filter: "blur(40px)",
        }}
      />

      {/* Secondary highlight — top right (slate accent) */}
      {!isNarrow && (
        <div
          className="absolute -top-10 right-0 h-[350px] w-[450px]"
          style={{
            background:
              "radial-gradient(ellipse at 80% 10%, var(--admin-hero-highlight), transparent 60%)",
            filter: "blur(50px)",
          }}
        />
      )}

      {/* Drifting conic gradient (desktop only, respect reduced motion) */}
      {!isNarrow && !prefersReducedMotion && (
        <div
          className="absolute left-1/4 top-10 h-[400px] w-[400px] opacity-60"
          style={{
            background: "var(--grad-admin-conic)",
            filter: "blur(60px)",
            animation: "orb-drift 40s ease-in-out infinite alternate",
          }}
        />
      )}

      {/* Third orb — bottom left (subtle indigo) */}
      <div
        className="absolute bottom-0 left-0 h-[300px] w-[400px]"
        style={{
          background: "radial-gradient(ellipse at 20% 80%, var(--admin-orb-3), transparent 65%)",
          filter: "blur(50px)",
        }}
      />
    </div>
  )
}
