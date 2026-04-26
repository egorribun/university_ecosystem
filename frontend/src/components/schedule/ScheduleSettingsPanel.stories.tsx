import type { Meta, StoryObj } from "@storybook/react-vite-vite"
import { ScheduleSettingsPanel } from "./ScheduleSettingsPanel"

const meta: Meta<typeof ScheduleSettingsPanel> = {
  title: "Schedule/ScheduleSettingsPanel",
  component: ScheduleSettingsPanel,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof ScheduleSettingsPanel>

export const Default: Story = {
  args: {
    open: true,
    onClose: () => console.warn("Close"),
    weekdayLabels: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
    currentParity: "odd",
    setCurrentParity: (p) => console.warn("Set parity:", p),
  },
}

export const EvenParity: Story = {
  args: {
    ...Default.args,
    currentParity: "even",
  },
}
