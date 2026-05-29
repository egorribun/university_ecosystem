import type { Decorator, Meta, StoryObj } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import AsyncImage from "./AsyncImage"

// AsyncImage uses framer-motion m.img for the fade-in → LazyMotion decorator.
const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
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
    </LazyMotion>
  )
}

const meta: Meta<typeof AsyncImage> = {
  title: "Media/AsyncImage",
  component: AsyncImage,
  tags: ["autodocs"],
  parameters: { layout: "centered" },
}

export default meta
type Story = StoryObj<typeof AsyncImage>

export const Default: Story = {
  args: {
    src: "https://picsum.photos/seed/async-image/640/400",
    alt: "Lazy-loaded campus photo",
    className: "h-[200px] w-[320px]",
  },
  decorators: [themed(false)],
}

export const Fallback: Story = {
  args: { alt: "No image", className: "h-[200px] w-[320px]" },
  decorators: [themed(false)],
  parameters: { docs: { description: { story: "No src → centered image-placeholder icon." } } },
}

export const DarkMode: Story = {
  args: {
    src: "https://picsum.photos/seed/async-image/640/400",
    alt: "Lazy-loaded campus photo",
    className: "h-[200px] w-[320px]",
  },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
