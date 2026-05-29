import type { Decorator, Meta, StoryObj } from "@storybook/react-vite"
import { StoryCircle } from "./StoryCircle"

const Avatar = () => (
  <img
    src="https://i.pravatar.cc/96?img=12"
    alt=""
    className="h-full w-full rounded-full object-cover"
  />
)

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div
        style={{
          background: "var(--bg-page)",
          padding: "2rem",
          display: "flex",
          gap: "1.5rem",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Story />
      </div>
    </div>
  )
}

const meta: Meta<typeof StoryCircle> = {
  title: "UI/StoryCircle",
  component: StoryCircle,
  tags: ["autodocs"],
  parameters: { layout: "centered" },
}

export default meta
type Story = StoryObj<typeof StoryCircle>

export const Small: Story = {
  args: { size: "sm", children: <Avatar /> },
  decorators: [themed(false)],
}

export const Medium: Story = {
  args: { size: "md", children: <Avatar /> },
  decorators: [themed(false)],
}

export const Large: Story = {
  args: { size: "lg", children: <Avatar /> },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { size: "md", children: <Avatar /> },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
