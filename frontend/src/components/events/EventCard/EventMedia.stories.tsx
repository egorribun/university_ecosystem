import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { EventMedia } from "./EventMedia"

// Wave 196 SW4 — EventMedia Storybook fixture (CONTEXT-tier kickoff).
//
// Event-card media area: SmartImage cover + gradient overlay + event-type badge +
// live/soon status indicators. Renders from props alone (imageUrl/alt/eventType/
// timeStatus/isReady/onReady/onImageClick). `.events-theme` supplies the
// `event-media-*` tokens; labels via I18nextProvider. No framer-motion (CSS
// animate-ping/pulse). `group` host enables the hover overlay. The picsum image is
// external network (filtered as smoke noise); SmartImage falls back gracefully.
//
// Variants: Default (none + type badge) / Live / Soon / DarkMode.

const baseArgs = {
  imageUrl: "https://picsum.photos/seed/ue-event/640/360",
  alt: "Event banner",
  eventType: "Workshop",
  isReady: true,
  onReady: () => {},
  onImageClick: () => {},
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div className="events-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div className="group" style={{ width: 360 }}>
          <Story />
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof EventMedia> = {
  title: "Events/EventMedia",
  component: EventMedia,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof EventMedia>

export const Default: Story = {
  args: { ...baseArgs, timeStatus: { status: "none" } },
  decorators: [themed(false)],
}

export const Live: Story = {
  args: { ...baseArgs, timeStatus: { status: "live" } },
  decorators: [themed(false)],
}

export const Soon: Story = {
  args: { ...baseArgs, timeStatus: { status: "soon", timeText: "2h" } },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { ...baseArgs, timeStatus: { status: "live" } },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
