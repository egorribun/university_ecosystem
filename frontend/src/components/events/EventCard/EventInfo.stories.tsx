import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { EventInfo } from "./EventInfo"

// Wave 196 SW4 — EventInfo Storybook fixture (CONTEXT-tier kickoff).
//
// Event-detail info block (title + speaker + date range + location + description,
// with Tooltip-wrapped icons). Renders from primitive props + the global I18next
// decorator alone. `.events-theme` supplies `text-brand` + `via-event-divider`.
// No framer-motion. The component returns a fragment, so the decorator wraps it in
// a card host.
//
// Variants: Default (with speaker) / NoSpeaker / DarkMode.

const baseArgs = {
  titleId: "evt-info-title",
  title: "International Symposium on Quantum Computing",
  speaker: "Prof. Petrov",
  startsAt: "2026-06-20T10:00:00Z",
  endsAt: "2026-06-20T12:00:00Z",
  location: "Grand Auditorium",
  description:
    "Explore the frontiers of quantum computing with leading researchers across error correction, hardware, and algorithms.",
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div className="events-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div
          className="rounded-2xl border border-glass-border bg-surface p-5"
          style={{ maxWidth: 460 }}
        >
          <Story />
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof EventInfo> = {
  title: "Events/EventInfo",
  component: EventInfo,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof EventInfo>

export const Default: Story = {
  args: { ...baseArgs },
  decorators: [themed(false)],
}

export const NoSpeaker: Story = {
  args: { ...baseArgs, speaker: undefined },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { ...baseArgs },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
