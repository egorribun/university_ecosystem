import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { EventsBackdrop } from "./EventsBackdrop"

// Wave 193 SW4 — EventsBackdrop Storybook fixture.
//
// 2-prop family (isNarrow + prefersReducedMotion, no isMobile). Amber
// ambient orbs scoped under `.events-theme` (tokens/events.css), so the
// `themed(dark)` factory (W193 SW2 pattern) wraps in `.events-theme` with
// `.dark` as an ANCESTOR for the dark variant. Production wrapper:
// EventsFeature.tsx:212.
//
// Variants: Default / DarkMode / Narrow / ReducedMotion (no Mobile — the
// 2-prop family has no isMobile distinction).

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div
        className="events-theme relative h-[600px] w-full overflow-hidden"
        style={{ background: "var(--bg-page)" }}
      >
        <Story />
        <div className="relative z-base flex h-full items-center justify-center text-sm text-(--text-secondary)">
          <span>Events surface — amber orbs render behind this text</span>
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof EventsBackdrop> = {
  title: "Events/EventsBackdrop",
  component: EventsBackdrop,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof EventsBackdrop>

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
