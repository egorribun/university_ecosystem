import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { MapHeader } from "./MapHeader"

// Wave 196 SW1 — MapHeader Storybook fixture (LEAF tier batch 2).
//
// Unified page header (icon + i18n title + inline badge) matching the
// News/Schedule/Events/Activity cross-page pattern. Zero props — the content is
// i18n-driven via the global I18nextProvider. Wraps its row in `<FadeSection>`
// (framer-motion `m.*`) → LazyMotion decorator. `.map-theme` supplies the
// `.map-badge-matte` + `--map-accent-icon` tokens. `pauseAnimationAtEnd` freezes
// the FadeSection entrance for deterministic Chromatic snapshots.
//
// Variants: Default / DarkMode.

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div className="map-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
          <Story />
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof MapHeader> = {
  title: "Map/MapHeader",
  component: MapHeader,
  parameters: {
    layout: "fullscreen",
    chromatic: { pauseAnimationAtEnd: true },
  },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof MapHeader>

export const Default: Story = {
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
