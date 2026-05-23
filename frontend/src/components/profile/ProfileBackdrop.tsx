/**
 * ProfileBackdrop — decorative ambient gradient layer for /profile page.
 *
 * Wave 184 SW5 (Path D) — Profile polish to feature-page parity with
 * W181-W183 messenger polish arc. Pattern mirrors MessengerBackdrop.tsx
 * (W181 SW2) which itself mirrors FooterBackdrop.tsx (W176 SW2 / EventsBackdrop
 * W118 SW3 CLS-118-03 lesson — pixel-based orb sizing eliminates CLS
 * shifts when container content grows; %-based sizing was the W118 culprit).
 *
 * 3 orbs (rose-primary, pink-warm-accent, amber-cozy-tertiary) layered
 * behind ProfileHeader + ProfileDetails so the Profile page reads as
 * warm/personal/identity-centric rather than the flat glass-on-page
 * appearance pre-W184. Tokens (`--profile-orb-1/2/3`) defined in
 * `tokens/profile.css` for both light + dark themes.
 *
 * `prefersReducedMotion` prop drops `filter: blur(...)` on each orb to
 * save mobile GPU + give a flatter look for users who opted into reduced
 * motion via OS preference. `isNarrow` prop scales orbs down for
 * sub-content-breakpoint viewports (~< 900px) so mobile/tablet doesn't
 * have orbs overflowing the narrower stage.
 *
 * Anchoring: ALL orbs use `top:` (NOT `bottom:`) per W118 SW3 CLS-118-03 —
 * Profile content varies in height (ProfileHeader + edit mode vs view
 * mode + achievements list grows over time) so bottom-anchored orbs
 * would shift unpredictably.
 */

interface ProfileBackdropProps {
  isNarrow?: boolean
  isMobile?: boolean
  prefersReducedMotion?: boolean
}

export function ProfileBackdrop({
  isNarrow = false,
  isMobile = false,
  prefersReducedMotion = false,
}: ProfileBackdropProps) {
  // Wave 184 SW5 — mobile GPU mitigation mirrors MessengerBackdrop W183 SW7
  // pattern (drop `filter: blur(...)` on mobile OR reduced-motion). Tablets
  // (isNarrow but not isMobile) keep the blur — modern tablet GPUs handle
  // 3 full-viewport radial blur orbs without frame drops.
  const dropBlur = prefersReducedMotion || isMobile

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden -z-1" aria-hidden="true">
      {/* Primary rose glow — large radial top-center. Sits at the visual
          weight-center of the upper portion of the Profile viewport
          (behind ProfileHeader). Adds premium warm depth without
          competing with the user's avatar/name as visual focus. */}
      <div
        className="absolute rounded-full"
        style={{
          width: isNarrow ? "120%" : "85%",
          height: isNarrow ? "380px" : "520px",
          top: isNarrow ? "-120px" : "-160px",
          left: "50%",
          transform: "translateX(-50%)",
          background: "radial-gradient(ellipse at center, var(--profile-orb-1), transparent 70%)",
          filter: dropBlur ? "none" : "blur(60px)",
          opacity: 0.6,
        }}
      />

      {/* Secondary pink warm accent — right side anchored from top.
          Gives a warm complementary tone that distinguishes Profile from
          cool-only surfaces (Map teal, Footer blue). Behind right column
          (ProfileDetails / AchievementsSection / Edit form). */}
      <div
        className="absolute rounded-full"
        style={{
          width: isNarrow ? "60%" : "42%",
          height: isNarrow ? "240px" : "320px",
          top: isNarrow ? "60px" : "100px",
          right: isNarrow ? "-12%" : "-6%",
          background: "radial-gradient(ellipse at center, var(--profile-orb-2), transparent 70%)",
          filter: dropBlur ? "none" : "blur(70px)",
          opacity: 0.5,
        }}
      />

      {/* Tertiary amber cozy sheen — bottom-left area, top-anchored
          for CLS stability. Adds a warm/sand counterpoint to the rose+pink
          and gives Profile a uniquely "personal/cozy" feel vs other
          themed surfaces. Distinct from Events amber-400/500 (this is
          amber-300, lighter + warmer). */}
      <div
        className="absolute rounded-full"
        style={{
          width: isNarrow ? "70%" : "38%",
          height: isNarrow ? "240px" : "300px",
          top: isNarrow ? "320px" : "400px",
          left: isNarrow ? "-10%" : "5%",
          background: "radial-gradient(ellipse at center, var(--profile-orb-3), transparent 70%)",
          filter: dropBlur ? "none" : "blur(55px)",
          opacity: 0.4,
        }}
      />
    </div>
  )
}

export default ProfileBackdrop
