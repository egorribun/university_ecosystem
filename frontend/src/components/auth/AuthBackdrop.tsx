/**
 * AuthBackdrop — decorative ambient gradient layer for auth pages
 * (/login + /register + /forgot-password + /reset-password).
 *
 * Wave 186 SW2 (Path C) — Auth pages polish to feature-page parity
 * with W181-W184 polish arc. Pattern mirrors ProfileBackdrop.tsx
 * (W184 SW5) + MessengerBackdrop.tsx (W181 SW2) which themselves
 * mirror FooterBackdrop.tsx (W176 SW2 / EventsBackdrop W118 SW3
 * CLS-118-03 lesson — pixel-based orb sizing eliminates CLS
 * shifts when container content grows; %-based sizing was the
 * W118 culprit).
 *
 * 3 orbs (teal-primary, cyan-cool-accent, teal-light-sheen)
 * layered behind the auth card so the auth surface reads as
 * "secure access" / cool/calm rather than the flat
 * particle-canvas-only appearance pre-W186. Tokens
 * (`--auth-orb-1/2/3`) defined in `tokens/auth.css` for both
 * light + dark themes.
 *
 * Coexists with ParticleAuthBackground (W113 SW6) on Login +
 * Register: AuthBackdrop renders static-orb ambient depth at
 * `-z-1`; ParticleAuthBackground renders 1000-particle canvas
 * overlay on top (different visual layer, both contribute to
 * the auth-surface aesthetic). On ForgotPassword + ResetPassword
 * AuthBackdrop REPLACES inline hardcoded glow blocks (~20 lines
 * of duplicated code per page becomes single component call).
 *
 * `prefersReducedMotion` prop drops `filter: blur(...)` on each
 * orb to save mobile GPU + give a flatter look for users who
 * opted into reduced motion via OS preference. `isNarrow` prop
 * scales orbs down for sub-content-breakpoint viewports
 * (~< 900px).
 *
 * Anchoring: ALL orbs use `top:` (NOT `bottom:`) per W118 SW3
 * CLS-118-03 — auth page content varies by route (Login compact
 * + Register tall + Reset/Forgot modal) so bottom-anchored orbs
 * would shift unpredictably across the 4 routes.
 */

interface AuthBackdropProps {
  isNarrow?: boolean
  isMobile?: boolean
  prefersReducedMotion?: boolean
}

export function AuthBackdrop({
  isNarrow = false,
  isMobile = false,
  prefersReducedMotion = false,
}: AuthBackdropProps) {
  // Wave 186 SW2 — mobile GPU mitigation mirrors MessengerBackdrop
  // W183 SW7 + ProfileBackdrop W184 SW5 pattern (drop `filter: blur(...)`
  // on mobile OR reduced-motion). Tablets (isNarrow but not isMobile)
  // keep the blur — modern tablet GPUs handle 3 full-viewport radial
  // blur orbs without frame drops.
  const dropBlur = prefersReducedMotion || isMobile

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden -z-1" aria-hidden="true">
      {/* Primary teal glow — large radial top-center. Sits at the visual
          weight-center of the upper portion of the auth viewport (behind
          the auth card on Login + behind hero panel on Register).
          "Secure access" semantics — teal-500 (darker than Map's
          teal-400 primary) communicates calm/safety better than warm
          tones (which would feel anxious in a sensitive credential-
          entry context). */}
      <div
        className="absolute rounded-full"
        style={{
          width: isNarrow ? "120%" : "85%",
          height: isNarrow ? "380px" : "520px",
          top: isNarrow ? "-120px" : "-160px",
          left: "50%",
          transform: "translateX(-50%)",
          background: "radial-gradient(ellipse at center, var(--auth-orb-1), transparent 70%)",
          filter: dropBlur ? "none" : "blur(60px)",
          opacity: 0.6,
        }}
      />

      {/* Secondary cyan cool accent — right side anchored from top.
          Gives a cool complementary tone within the teal/cyan palette
          family. Behind right column on Login/Register grid layouts,
          and behind right edge of centered modals on Reset/Forgot. */}
      <div
        className="absolute rounded-full"
        style={{
          width: isNarrow ? "60%" : "42%",
          height: isNarrow ? "240px" : "320px",
          top: isNarrow ? "60px" : "100px",
          right: isNarrow ? "-12%" : "-6%",
          background: "radial-gradient(ellipse at center, var(--auth-orb-2), transparent 70%)",
          filter: dropBlur ? "none" : "blur(70px)",
          opacity: 0.5,
        }}
      />

      {/* Tertiary teal-light sheen — bottom-left area, top-anchored for
          CLS stability. Adds depth without competing with primary teal
          (uses lighter shade — teal-400 vs teal-500 primary). Ties the
          palette together with the primary while remaining subtle. */}
      <div
        className="absolute rounded-full"
        style={{
          width: isNarrow ? "70%" : "38%",
          height: isNarrow ? "240px" : "300px",
          top: isNarrow ? "320px" : "400px",
          left: isNarrow ? "-10%" : "5%",
          background: "radial-gradient(ellipse at center, var(--auth-orb-3), transparent 70%)",
          filter: dropBlur ? "none" : "blur(55px)",
          opacity: 0.4,
        }}
      />
    </div>
  )
}

export default AuthBackdrop
