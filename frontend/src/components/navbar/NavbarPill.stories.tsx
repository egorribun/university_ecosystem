import type { Decorator, Meta, StoryObj } from "@storybook/react-vite"
import { NavbarPill } from "./NavbarPill"

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <Story />
      </div>
    </div>
  )
}

const sampleChildren = (
  <div className="flex w-full items-center justify-between px-2">
    <span className="font-black tracking-tight text-text-primary">ГУУ Экосистема</span>
    <span className="text-sm text-(--text-secondary)">Dashboard · News · Events</span>
  </div>
)

const meta: Meta<typeof NavbarPill> = {
  title: "Navbar/NavbarPill",
  component: NavbarPill,
  tags: ["autodocs"],
  parameters: {
    layout: "fullscreen",
    // Compact pill has a 6s breathing animation — freeze for Chromatic.
    chromatic: { pauseAnimationAtEnd: true },
  },
}

export default meta
type Story = StoryObj<typeof NavbarPill>

export const Expanded: Story = {
  args: { isCompact: false, prefersReducedMotion: false, children: sampleChildren },
  decorators: [themed(false)],
}

export const Compact: Story = {
  args: { isCompact: true, prefersReducedMotion: false, children: sampleChildren },
  decorators: [themed(false)],
  parameters: {
    docs: {
      description: { story: "Compact pill — glass bg, layered shadows, inner glow, breathing." },
    },
  },
}

export const DarkMode: Story = {
  args: { isCompact: true, prefersReducedMotion: false, children: sampleChildren },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
