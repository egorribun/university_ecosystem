import { useEffect, type ReactNode } from "react"
import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import BackToTop from "./BackToTop"

// Wave 200 SW1 — BackToTop story (campaign close: the last storyable component).
//
// BackToTop has TWO browser-signal gates, handled differently:
//   1. Scroll gate (BackToTop.tsx:18-23) — a `scroll` listener sets
//      `show = window.scrollY > 420`. VALUE-readable: the ScrollGate harness
//      redefines `window.scrollY` + dispatches a synthetic `scroll` event
//      (deferred via rAF so BackToTop's own mount-effect listener is attached
//      first) to deterministically reveal/hide the FAB. Chromium (used by both
//      Chromatic and the runtime smoke) permits redefining `scrollY`.
//   2. Footer-offset gate (BackToTop.tsx:26-47) — an IntersectionObserver on
//      `[role=contentinfo]` lifts the FAB above the footer. LAYOUT-driven, NOT
//      value-driven: faking scrollY does NOT fire it, and real scroll is
//      Chromatic-flaky. A static `<footer role="contentinfo">` is placed well
//      below the fold ONLY so the observer's attach branch runs (it null-guards
//      at line 28 otherwise); it reports not-intersecting → the FAB stays at its
//      default bottom:24. Footer-aware repositioning is a deliberate non-goal
//      (AUDIT_WAVE200 §Honesty).
//
// Variants: Default (scrolled, light) / DarkMode / BelowThreshold (hidden).

const ScrollGate = ({ scrolled, children }: { scrolled: boolean; children: ReactNode }) => {
  useEffect(() => {
    Object.defineProperty(window, "scrollY", {
      value: scrolled ? 600 : 0,
      configurable: true,
      writable: true,
    })
    const id = requestAnimationFrame(() => window.dispatchEvent(new Event("scroll")))
    return () => {
      cancelAnimationFrame(id)
      Object.defineProperty(window, "scrollY", { value: 0, configurable: true, writable: true })
    }
  }, [scrolled])
  return <>{children}</>
}

const themed = (dark: boolean, scrolled: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div
          style={{
            background: "var(--bg-page)",
            minHeight: "100vh",
            position: "relative",
            padding: "2rem",
          }}
        >
          <p style={{ color: "var(--text-secondary)", maxWidth: "32rem" }}>
            The back-to-top FAB appears in the bottom-right corner once the page is scrolled past
            420px.
          </p>
          <ScrollGate scrolled={scrolled}>
            <Story />
          </ScrollGate>
          {/* Static footer (below the fold) so the FAB's IntersectionObserver attach branch runs. */}
          <footer
            role="contentinfo"
            style={{ position: "absolute", left: 0, right: 0, top: "140vh", height: 200 }}
          />
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof BackToTop> = {
  title: "Motion/BackToTop",
  component: BackToTop,
  parameters: { layout: "fullscreen", chromatic: { pauseAnimationAtEnd: true } },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof BackToTop>

export const Default: Story = { decorators: [themed(false, true)] }

export const DarkMode: Story = {
  decorators: [themed(true, true)],
  parameters: { backgrounds: { default: "dark" } },
}

export const BelowThreshold: Story = { decorators: [themed(false, false)] }
