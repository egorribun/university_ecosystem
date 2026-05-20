/**
 * FooterBackdrop — decorative ambient gradient layer for site-wide footer.
 *
 * Pattern source: `components/events/EventsBackdrop.tsx` (Wave 118 SW3
 * CLS-118-03 lesson — pixel-based orb sizing eliminates CLS shifts when
 * container content grows; %-based sizing was the W118 culprit).
 *
 * Wave 176 SW2 — 3 orbs (sky-glow primary, indigo highlight, white sheen)
 * layered above the W175 SW1 `bg-footer` premium blue gradient (light) /
 * nav-dark gradient (dark). Tokens (`--footer-orb-primary`,
 * `--footer-orb-secondary`, `--footer-orb-sheen`) defined in
 * `tokens/semantics.css` for both light + dark themes.
 *
 * Footer is theme-AGNOSTIC always-dark surface (per W175 SW1 invariant)
 * — orbs intentionally use cooler hues that work on BOTH the blue
 * gradient AND the nav-dark gradient.
 *
 * `prefersReducedMotion` prop drops `filter: blur(...)` on each orb to
 * save mobile GPU + give a flatter look for users who opted into reduced
 * motion via OS preference (the actual entrance animation is on the
 * footer container itself via Tailwind v4 `starting:` — see SW3).
 *
 * `isNarrow` prop scales orbs down for sub-900px viewports. Footer
 * columns stack from 5→2→1 cols below `lg`/`sm` Tailwind breakpoints; orbs
 * follow the same visual rhythm.
 */

interface FooterBackdropProps {
  isNarrow?: boolean
  prefersReducedMotion?: boolean
}

export function FooterBackdrop({
  isNarrow = false,
  prefersReducedMotion = false,
}: FooterBackdropProps) {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden -z-1" aria-hidden="true">
      {/* Primary glow — large sky radial top-center. Sits ABOVE the blue
          gradient base and adds depth without changing the dominant hue. */}
      <div
        className="absolute rounded-full"
        style={{
          width: isNarrow ? "120%" : "85%",
          height: isNarrow ? "320px" : "460px",
          top: "-120px",
          left: "50%",
          transform: "translateX(-50%)",
          background:
            "radial-gradient(ellipse at center, var(--footer-orb-primary), transparent 70%)",
          filter: prefersReducedMotion ? "none" : "blur(50px)",
          opacity: 0.6,
        }}
      />

      {/* Secondary highlight — indigo accent on the right side. Anchored
          from the top so footer content growth doesn't shift the orb
          (W118 SW3 CLS-118-03). */}
      <div
        className="absolute rounded-full"
        style={{
          width: isNarrow ? "55%" : "40%",
          height: isNarrow ? "180px" : "260px",
          top: "20px",
          right: "-8%",
          background:
            "radial-gradient(ellipse at center, var(--footer-orb-secondary), transparent 70%)",
          filter: prefersReducedMotion ? "none" : "blur(60px)",
          opacity: 0.45,
        }}
      />

      {/* Tertiary sheen — subtle white glow bottom-left. Soft brightening
          on the copyright row. Anchored from top, NOT from bottom, so
          footer content growth keeps it stable. */}
      <div
        className="absolute rounded-full"
        style={{
          width: isNarrow ? "60%" : "35%",
          height: isNarrow ? "200px" : "240px",
          top: isNarrow ? "240px" : "300px",
          left: isNarrow ? "-10%" : "5%",
          background:
            "radial-gradient(ellipse at center, var(--footer-orb-sheen), transparent 70%)",
          filter: prefersReducedMotion ? "none" : "blur(50px)",
          opacity: 0.3,
        }}
      />
    </div>
  )
}

export default FooterBackdrop
