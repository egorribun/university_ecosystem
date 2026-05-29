import type { Decorator, Meta, StoryObj } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { ProfileSkeleton } from "./ProfileSkeleton"

// Wraps <Layout> (uses framer-motion m.*) → LazyMotion decorator required.
// Layout brings min-h-screen + bg-page, so it renders full-page on its own.
const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <Story />
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof ProfileSkeleton> = {
  title: "Profile/ProfileSkeleton",
  component: ProfileSkeleton,
  tags: ["autodocs"],
  parameters: { layout: "fullscreen" },
}

export default meta
type Story = StoryObj<typeof ProfileSkeleton>

export const Default: Story = { decorators: [themed(false)] }

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
