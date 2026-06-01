import type { Decorator, Meta, StoryObj } from "@storybook/react-vite"
import SmartImage from "./SmartImage"

// SmartImage routes through the image proxy (resolveProxyImageUrl); when the
// proxy backend isn't running (e.g. Storybook), it falls back to the placeholder.
const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div
        style={{
          background: "var(--bg-page)",
          padding: "2rem",
          display: "flex",
          justifyContent: "center",
        }}
      >
        <Story />
      </div>
    </div>
  )
}

const meta: Meta<typeof SmartImage> = {
  title: "Media/SmartImage",
  component: SmartImage,
  tags: ["autodocs"],
  parameters: { layout: "centered" },
}

export default meta
type Story = StoryObj<typeof SmartImage>

export const Default: Story = {
  args: {
    srcRaw: "https://picsum.photos/seed/smart-image/640/400",
    alt: "Campus photo",
    className: "h-[200px] w-[320px] rounded-lg",
  },
  decorators: [themed(false)],
}

export const Fallback: Story = {
  args: { alt: "Placeholder", className: "h-[200px] w-[320px] rounded-lg" },
  decorators: [themed(false)],
  parameters: {
    docs: { description: { story: "No srcRaw → renders the IMAGE_PLACEHOLDER_URL fallback." } },
  },
}

export const DarkMode: Story = {
  args: {
    srcRaw: "https://picsum.photos/seed/smart-image/640/400",
    alt: "Campus photo",
    className: "h-[200px] w-[320px] rounded-lg",
  },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
