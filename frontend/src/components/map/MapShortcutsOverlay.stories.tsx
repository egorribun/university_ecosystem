import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { MapShortcutsOverlay } from "./MapShortcutsOverlay"

// Wave 196 SW1 — MapShortcutsOverlay Storybook fixture (LEAF tier batch 2).
//
// Keyboard-shortcuts help dialog for the campus map. Controlled via `open` +
// `onClose` props (unlike the Events/News shortcut overlays, which self-toggle
// on a "?"-keypress and render null statically — those are SKIP). Story passes
// `open: true` to render the full dialog. Uses framer-motion `m.*` +
// AnimatePresence + useFocusTrap → LazyMotion decorator. `.map-theme` supplies
// `.map-card-matte` / `.matte-chip` / `--map-overlay-bg` tokens. layout
// fullscreen (the overlay is `fixed inset-0 z-modal`); `pauseAnimationAtEnd`
// freezes the spring entrance for Chromatic.
//
// Variants: Default (open dialog) / DarkMode.

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div className="map-theme" style={{ background: "var(--bg-page)", minHeight: "100vh" }}>
          <Story />
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof MapShortcutsOverlay> = {
  title: "Map/MapShortcutsOverlay",
  component: MapShortcutsOverlay,
  parameters: {
    layout: "fullscreen",
    chromatic: { pauseAnimationAtEnd: true },
  },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof MapShortcutsOverlay>

export const Default: Story = {
  args: { open: true, onClose: () => {} },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { open: true, onClose: () => {} },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
