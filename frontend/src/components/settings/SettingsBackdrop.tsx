/**
 * SettingsBackdrop — decorative ambient gradient layer for /settings page.
 *
 * Wave 184 SW6 (Path D) — Settings polish to feature-page parity with
 * W181-W183 messenger arc + paired with ProfileBackdrop W184 SW5.
 *
 * Pattern mirrors ProfileBackdrop.tsx (W184 SW5) which itself mirrors
 * MessengerBackdrop.tsx (W181 SW2) which mirrors FooterBackdrop.tsx
 * (W176 SW2 / EventsBackdrop W118 SW3 CLS-118-03 lesson).
 *
 * DIFFERENCES vs Profile/Messenger Backdrops:
 * - 4 orbs (vs 3) — Settings has a 4-tab horizontal layout so the visual
 *   weight is distributed across a wider stage (General | Account |
 *   Security | Integrations tabs). 4th orb sits at the right edge to
 *   balance the visual gravity.
 * - Slate-500 + purple-400 + slate-300 palette (neutral/technical/config
 *   semantics) — distinct from rose-warm Profile palette.
 *
 * SHARED:
 * - All orbs use `top:` (NOT `bottom:`) per W118 SW3 CLS-118-03 — Settings
 *   tabpanel height varies wildly (General tab is short, Security tab
 *   with sessions list is tall). Bottom-anchored orbs would shift
 *   unpredictably as user switches tabs.
 * - `prefersReducedMotion` drops `filter: blur(...)` for GPU mitigation.
 * - `isNarrow` scales orbs down for sub-content-breakpoint viewports.
 * - Settings backdrop MUST conditional render gated on `isSettings`
 *   (route-level) NOT on active tab — FIX-77-03 pattern. Tab transitions
 *   should NOT cause backdrop to re-mount/flash.
 */

interface SettingsBackdropProps {
  isNarrow?: boolean
  isMobile?: boolean
  prefersReducedMotion?: boolean
}

export function SettingsBackdrop({
  isNarrow = false,
  isMobile = false,
  prefersReducedMotion = false,
}: SettingsBackdropProps) {
  const dropBlur = prefersReducedMotion || isMobile

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden -z-1" aria-hidden="true">
      {/* Primary slate glow — large radial top-center. Sits at the visual
          weight-center of the upper portion of Settings (behind the Settings
          title + tab strip). Slate-tone reads as "technical/quiet" — config
          page shouldn't shout. */}
      <div
        className="absolute rounded-full"
        style={{
          width: isNarrow ? "120%" : "85%",
          height: isNarrow ? "380px" : "520px",
          top: isNarrow ? "-120px" : "-160px",
          left: "50%",
          transform: "translateX(-50%)",
          background: "radial-gradient(ellipse at center, var(--settings-orb-1), transparent 70%)",
          filter: dropBlur ? "none" : "blur(60px)",
          opacity: 0.6,
        }}
      />

      {/* Secondary purple cool accent — right side anchored from top.
          Purple-400 is the unique-to-Settings accent that distinguishes
          this surface from the otherwise-slate-quiet palette. Behind
          the right portion of the tabpanel (where SettingsSecurity's
          MFA + sessions panels live). */}
      <div
        className="absolute rounded-full"
        style={{
          width: isNarrow ? "60%" : "42%",
          height: isNarrow ? "240px" : "320px",
          top: isNarrow ? "60px" : "100px",
          right: isNarrow ? "-12%" : "-6%",
          background: "radial-gradient(ellipse at center, var(--settings-orb-2), transparent 70%)",
          filter: dropBlur ? "none" : "blur(70px)",
          opacity: 0.5,
        }}
      />

      {/* Tertiary lighter slate sheen — bottom-left area, top-anchored
          for CLS stability. Adds depth variation within the slate
          monochrome (slate-300 vs slate-500 primary) without introducing
          a different hue. */}
      <div
        className="absolute rounded-full"
        style={{
          width: isNarrow ? "70%" : "38%",
          height: isNarrow ? "240px" : "300px",
          top: isNarrow ? "320px" : "400px",
          left: isNarrow ? "-10%" : "5%",
          background: "radial-gradient(ellipse at center, var(--settings-orb-3), transparent 70%)",
          filter: dropBlur ? "none" : "blur(55px)",
          opacity: 0.4,
        }}
      />

      {/* Quaternary right-edge slate balancer — Settings has 4-tab
          horizontal layout; this 4th orb sits at the right-edge to
          balance visual weight across the wider stage. Top-anchored
          slightly lower than orb-2 to avoid overlap. */}
      <div
        className="absolute rounded-full"
        style={{
          width: isNarrow ? "55%" : "32%",
          height: isNarrow ? "220px" : "280px",
          top: isNarrow ? "240px" : "320px",
          right: isNarrow ? "-15%" : "-8%",
          background: "radial-gradient(ellipse at center, var(--settings-orb-4), transparent 70%)",
          filter: dropBlur ? "none" : "blur(65px)",
          opacity: 0.35,
        }}
      />
    </div>
  )
}

export default SettingsBackdrop
