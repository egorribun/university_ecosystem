import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { MapBackdrop } from "./MapBackdrop"

// Wave 193 SW4 — MapBackdrop Storybook fixture.
//
// 2-prop family (isNarrow + prefersReducedMotion, BOTH REQUIRED, no
// isMobile). Teal/cyan ambient orbs scoped under `.map-theme`
// (tokens/map.css), so the `themed(dark)` factory wraps in `.map-theme`
// with `.dark` as an ANCESTOR for the dark variant. Production wrappers:
// Map.tsx:13, MapFeature.tsx:212. Both props REQUIRED — passed explicitly.
//
// Variants: Default / DarkMode / Narrow / ReducedMotion.

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div
        className="map-theme relative h-[600px] w-full overflow-hidden"
        style={{ background: "var(--bg-page)" }}
      >
        <Story />
        <div className="relative z-base flex h-full items-center justify-center text-sm text-(--text-secondary)">
          <span>Map surface — teal/cyan orbs render behind this text</span>
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof MapBackdrop> = {
  title: "Map/MapBackdrop",
  component: MapBackdrop,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof MapBackdrop>

export const Default: Story = {
  args: {
    isNarrow: false,
    prefersReducedMotion: false,
  },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: {
    isNarrow: false,
    prefersReducedMotion: false,
  },
  parameters: {
    backgrounds: { default: "dark" },
  },
  decorators: [themed(true)],
}

export const Narrow: Story = {
  args: {
    isNarrow: true,
    prefersReducedMotion: false,
  },
  parameters: {
    viewport: {
      defaultViewport: "mobile1",
    },
  },
  decorators: [themed(false)],
}

export const ReducedMotion: Story = {
  args: {
    isNarrow: false,
    prefersReducedMotion: true,
  },
  decorators: [themed(false)],
}
