import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { EventActions } from "./EventActions"

// Wave 197 SW2 — EventActions Storybook fixture (CONTEXT-tier, cheap/ambient).
//
// Footer action row for an event card: participant count + register/unregister +
// QR check-in button (opens the nested EventQrDialog on click — closed at rest).
// Fully prop-driven; labels via the global I18nextProvider. The sessionStorage QR
// persistence is benign in Storybook.
//
// Variants: Active (open registration) / Registered (unregister + QR) / Ended /
// DarkMode.

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div className="events-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div
          className="rounded-2xl border border-glass-border bg-surface p-4"
          style={{ width: 360 }}
        >
          <Story />
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof EventActions> = {
  title: "Events/EventActions",
  component: EventActions,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
  args: {
    eventId: "e1",
    participantCount: 42,
    loading: false,
    onRegister: () => {},
    onUnregister: () => {},
  },
}

export default meta
type Story = StoryObj<typeof EventActions>

export const Active: Story = {
  args: { isActive: true, isEnded: false, isRegistered: false },
  decorators: [themed(false)],
}

export const Registered: Story = {
  args: { isActive: true, isEnded: false, isRegistered: true, qrToken: "demo-checkin-token" },
  decorators: [themed(false)],
}

export const Ended: Story = {
  args: { isActive: false, isEnded: true, isRegistered: false },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { isActive: true, isEnded: false, isRegistered: true, qrToken: "demo-checkin-token" },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
