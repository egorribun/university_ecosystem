import type { Decorator, Meta, StoryObj } from "@storybook/react-vite"
import EventCardHero from "./EventCardHero"

const IMG = "https://picsum.photos/seed/event-hero/720/400"
const STARTS = "2026-06-15T14:00:00Z"

/** Card-sized frame + `.events-theme` scope (events-badge-matte tokens). */
const framed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div className="events-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div
          className="group relative overflow-hidden rounded-2xl"
          style={{ width: 360, height: 200 }}
        >
          <Story />
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof EventCardHero> = {
  title: "Events/EventCardHero",
  component: EventCardHero,
  tags: ["autodocs"],
  parameters: {
    layout: "centered",
    // Shimmer + LIVE ping animate via CSS — freeze for deterministic Chromatic.
    chromatic: { pauseAnimationAtEnd: true },
  },
}

export default meta
type Story = StoryObj<typeof EventCardHero>

export const Default: Story = {
  args: { imageUrl: IMG, title: "University Festival 2026", startsAt: STARTS, timeStatus: "none" },
  decorators: [framed(false)],
}

export const Live: Story = {
  args: { ...Default.args, timeStatus: "live" },
  decorators: [framed(false)],
  parameters: {
    docs: { description: { story: "LIVE badge (top-right) when the event is in progress." } },
  },
}

export const StartingSoon: Story = {
  args: { ...Default.args, timeStatus: "soon" },
  decorators: [framed(false)],
}

export const NoImage: Story = {
  args: { title: "Career Fair", startsAt: STARTS, timeStatus: "none" },
  decorators: [framed(false)],
  parameters: {
    docs: { description: { story: "Fallback calendar icon when no image is supplied." } },
  },
}

export const DarkMode: Story = {
  args: { ...Default.args },
  decorators: [framed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
