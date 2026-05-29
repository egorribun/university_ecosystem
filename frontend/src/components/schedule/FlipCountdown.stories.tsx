import type { Meta, StoryObj } from "@storybook/react-vite"
import { FlipCountdown } from "./FlipCountdown"

const meta: Meta<typeof FlipCountdown> = {
  title: "Schedule/FlipCountdown",
  component: FlipCountdown,
  tags: ["autodocs"],
  parameters: {
    layout: "centered",
    // W201: live `new Date()`-relative countdown text drifts every build → skip snapshot.
    chromatic: { disableSnapshot: true },
  },
}

export default meta
type Story = StoryObj<typeof FlipCountdown>

export const FiveMinutes: Story = {
  args: {
    targetMinutes: new Date().getHours() * 60 + new Date().getMinutes() + 5,
  },
}

export const OneMinute: Story = {
  args: {
    targetMinutes: new Date().getHours() * 60 + new Date().getMinutes() + 1,
  },
}

export const Urgent: Story = {
  args: {
    // 30 seconds left
    targetMinutes: new Date().getHours() * 60 + new Date().getMinutes() + 0.5,
  },
}
