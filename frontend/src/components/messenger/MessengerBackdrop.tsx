/**
 * MessengerBackdrop — decorative ambient gradient layer for /messenger page.
 *
 * Pattern source: `components/layout/FooterBackdrop.tsx` (Wave 176 SW2,
 * itself mirroring `components/events/EventsBackdrop.tsx` Wave 118 SW3
 * CLS-118-03 lesson — pixel-based orb sizing eliminates CLS shifts when
 * container content grows; %-based sizing was the W118 culprit).
 *
 * Wave 181 SW2 — 3 orbs (violet-primary, pink-warm-accent, indigo-cool-sheen)
 * layered behind the chat-area `bg-msg-chat` surface and the sidebar
 * `bg-msg-sidebar` panel. Both surfaces are semi-opaque enough that the orbs
 * read as ambient depth (subtle hue shift) without distracting from chat
 * content. Tokens (`--messenger-orb-1/2/3`) defined in
 * `tokens/messenger.css` for both light + dark themes.
 *
 * `prefersReducedMotion` prop drops `filter: blur(...)` on each orb to
 * save mobile GPU + give a flatter look for users who opted into reduced
 * motion via OS preference (the actual entrance + scroll animations are
 * elsewhere — this prop is just the GPU-cost mitigation).
 *
 * `isNarrow` prop scales orbs down for sub-content-breakpoint viewports
 * (~< 900px). Mobile messenger is single-pane (full viewport for one of
 * sidebar OR chat); narrow orb sizing avoids overflow + keeps the visual
 * weight balanced for the smaller stage.
 *
 * Anchoring: ALL orbs use `top:` (NOT `bottom:`) per W118 SW3 CLS-118-03 —
 * messenger has variable chat-list length + variable message history height
 * which would shift bottom-anchored orbs unpredictably.
 */

interface MessengerBackdropProps {
  isNarrow?: boolean
  isMobile?: boolean
  prefersReducedMotion?: boolean
}

export function MessengerBackdrop({
  isNarrow = false,
  isMobile = false,
  prefersReducedMotion = false,
}: MessengerBackdropProps) {
  // Wave 183 SW7 — drop heavy `filter: blur(...)` on mobile OR when user
  // prefers reduced motion. Pre-W183 only the reduced-motion preference
  // gated blur removal, but mobile GPUs (especially older Android + Safari
  // mobile) suffer significantly from full-viewport radial blur filters
  // applied to 3 orbs simultaneously. Empirically dropping ~10-15 fps in
  // Chrome DevTools 4× CPU throttle simulation on a 414×896 viewport.
  // The orbs are still rendered (visual depth preserved); only the GPU-
  // expensive blur is dropped. Tablets (isNarrow but not isMobile) keep
  // the blur — they have desktop-class GPUs in most modern devices.
  const dropBlur = prefersReducedMotion || isMobile

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden -z-1" aria-hidden="true">
      {/* Primary violet glow — large radial top-center. Sits at the visual
          weight-center of the upper portion of the messenger viewport. Adds
          premium depth without changing the dominant hue of the chat surface. */}
      <div
        className="absolute rounded-full"
        style={{
          width: isNarrow ? "120%" : "85%",
          height: isNarrow ? "380px" : "520px",
          top: isNarrow ? "-120px" : "-160px",
          left: "50%",
          transform: "translateX(-50%)",
          background: "radial-gradient(ellipse at center, var(--messenger-orb-1), transparent 70%)",
          filter: dropBlur ? "none" : "blur(60px)",
          opacity: 0.6,
        }}
      />

      {/* Secondary pink warm accent — right side anchored from top (NOT
          bottom; W118 SW3 CLS-118-03). Gives a warm complementary tone
          that distinguishes messenger from cool-only surfaces like Map. */}
      <div
        className="absolute rounded-full"
        style={{
          width: isNarrow ? "60%" : "42%",
          height: isNarrow ? "240px" : "320px",
          top: isNarrow ? "60px" : "100px",
          right: isNarrow ? "-12%" : "-6%",
          background: "radial-gradient(ellipse at center, var(--messenger-orb-2), transparent 70%)",
          filter: dropBlur ? "none" : "blur(70px)",
          opacity: 0.5,
        }}
      />

      {/* Tertiary indigo cool sheen — bottom-left area, top-anchored for
          CLS stability. Adds cool counterpoint to the warm pink and ties
          the palette together with the deeper indigo cool tone. */}
      <div
        className="absolute rounded-full"
        style={{
          width: isNarrow ? "70%" : "38%",
          height: isNarrow ? "240px" : "300px",
          top: isNarrow ? "320px" : "400px",
          left: isNarrow ? "-10%" : "5%",
          background: "radial-gradient(ellipse at center, var(--messenger-orb-3), transparent 70%)",
          filter: dropBlur ? "none" : "blur(55px)",
          opacity: 0.4,
        }}
      />
    </div>
  )
}

export default MessengerBackdrop
