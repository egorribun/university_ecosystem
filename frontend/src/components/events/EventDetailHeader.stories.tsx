import type { Decorator, Meta, StoryObj } from "@storybook/react-vite"
import { EventDetailHeader } from "./EventDetailHeader"

const noop = () => {}

const baseArgs = {
  title: "AI Research Symposium 2026",
  eventType: "conference",
  participantCount: 248,
  startsAt: "2026-06-15T14:00:00Z",
  endsAt: "2026-06-15T18:00:00Z",
  location: "Main Auditorium, Bldg ГУК",
  speaker: "Prof. A. Ivanova",
  isRegistered: false,
  isEnded: false,
  isAdmin: false,
  registering: false,
  onShare: noop,
  onRegister: noop,
  onUnregister: noop,
  onEditOpen: noop,
  onDeleteOpen: noop,
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div className="events-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div style={{ maxWidth: 768, margin: "0 auto" }}>
          <Story />
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof EventDetailHeader> = {
  title: "Events/EventDetailHeader",
  component: EventDetailHeader,
  tags: ["autodocs"],
  parameters: { layout: "fullscreen" },
}

export default meta
type Story = StoryObj<typeof EventDetailHeader>

export const Default: Story = { args: baseArgs, decorators: [themed(false)] }

export const Registered: Story = {
  args: { ...baseArgs, isRegistered: true },
  decorators: [themed(false)],
  parameters: {
    docs: { description: { story: "Registered attendee — shows the Unregister action." } },
  },
}

export const Admin: Story = {
  args: { ...baseArgs, isAdmin: true },
  decorators: [themed(false)],
  parameters: {
    docs: { description: { story: "Admin view — Edit + Delete actions, no register CTA." } },
  },
}

export const Ended: Story = {
  args: { ...baseArgs, isEnded: true },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: baseArgs,
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
