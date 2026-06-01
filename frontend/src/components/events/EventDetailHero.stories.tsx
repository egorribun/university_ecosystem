import type { Decorator, Meta, StoryObj } from "@storybook/react-vite"
import { EventDetailHero } from "./EventDetailHero"

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

const meta: Meta<typeof EventDetailHero> = {
  title: "Events/EventDetailHero",
  component: EventDetailHero,
  tags: ["autodocs"],
  parameters: { layout: "fullscreen" },
}

export default meta
type Story = StoryObj<typeof EventDetailHero>

export const Default: Story = {
  args: { imageUrl: "https://picsum.photos/seed/event-detail/1200/675" },
  decorators: [themed(false)],
  parameters: {
    docs: { description: { story: "Hero image with a zoom-to-lightbox button (bottom-right)." } },
  },
}

export const DarkMode: Story = {
  args: { ...Default.args },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
