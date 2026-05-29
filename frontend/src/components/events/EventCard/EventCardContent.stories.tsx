import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import EventCardContent from "./EventCardContent"

// Wave 196 SW4 — EventCardContent Storybook fixture (CONTEXT-tier kickoff).
//
// Text-content section of an event card (title-as-Link, speaker, date range,
// location, description, participant count + status). Renders from primitive props
// + the global decorators alone: the title `<Link to="/events/$id">` resolves via
// preview.tsx's TanStack RouterProvider (proven by the W195 NewsDetailNavigation
// story), and labels via I18nextProvider. `.events-theme` supplies the
// `.events-card-*` tokens. No framer-motion. The `before:absolute` title overlay
// needs a `relative group` host (provided by the decorator).
//
// Variants: Open / Registered / Ended / DarkMode.

const baseArgs = {
  id: "e1",
  title: "React 19 Patterns Workshop",
  speaker: "Dr. Ivanova",
  startsAt: "2026-06-15T14:00:00Z",
  endsAt: "2026-06-15T16:00:00Z",
  location: "ГУК-305",
  description: "A hands-on deep dive into React 19 concurrent features and the new compiler.",
  participantCount: 42,
  isRegistered: false,
  isEnded: false,
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div className="events-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div
          className="group relative overflow-hidden rounded-2xl border border-glass-border bg-surface shadow-sm"
          style={{ width: 340 }}
        >
          <Story />
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof EventCardContent> = {
  title: "Events/EventCardContent",
  component: EventCardContent,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof EventCardContent>

export const Open: Story = {
  args: { ...baseArgs },
  decorators: [themed(false)],
}

export const Registered: Story = {
  args: { ...baseArgs, isRegistered: true },
  decorators: [themed(false)],
}

export const Ended: Story = {
  args: { ...baseArgs, isEnded: true },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { ...baseArgs, isRegistered: true },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
