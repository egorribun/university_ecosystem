import type { Decorator, Meta, StoryObj } from "@storybook/react-vite"
import { MediaSlot } from "./MediaSlot"

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div className="group" style={{ maxWidth: 360, margin: "0 auto" }}>
          <Story />
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof MediaSlot> = {
  title: "UI/MediaSlot",
  component: MediaSlot,
  tags: ["autodocs"],
  parameters: { layout: "fullscreen" },
}

export default meta
type Story = StoryObj<typeof MediaSlot>

export const Default: Story = {
  args: {
    src: "https://picsum.photos/seed/media-slot/640/360",
    alt: "Campus photo",
    aspectRatio: "16/9",
  },
  decorators: [themed(false)],
}

export const NoImage: Story = {
  args: { alt: "No image", aspectRatio: "16/9" },
  decorators: [themed(false)],
  parameters: { docs: { description: { story: "No src → centered image-icon fallback." } } },
}

export const Square: Story = {
  args: {
    src: "https://picsum.photos/seed/media-slot-sq/480/480",
    alt: "Square photo",
    aspectRatio: "1/1",
  },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { alt: "No image", aspectRatio: "16/9" },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
