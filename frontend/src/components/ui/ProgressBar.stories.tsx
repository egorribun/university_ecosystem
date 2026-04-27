import type { Meta, StoryObj } from "@storybook/react-vite"
import { ProgressBar } from "./ProgressBar"

const meta: Meta<typeof ProgressBar> = {
  title: "UI/ProgressBar",
  component: ProgressBar,
  tags: ["autodocs"],
  argTypes: {
    value: {
      control: { type: "range", min: 0, max: 100 },
    },
    max: {
      control: "number",
    },
    animated: {
      control: "boolean",
    },
    liveRegion: {
      control: "boolean",
    },
  },
}

export default meta
type Story = StoryObj<typeof ProgressBar>

export const Default: Story = {
  args: {
    value: 50,
    max: 100,
    animated: true,
  },
}

export const Success: Story = {
  args: {
    ...Default.args,
    value: 100,
    barClassName: "bg-success",
  },
}

export const Warning: Story = {
  args: {
    ...Default.args,
    value: 30,
    barClassName: "bg-warning",
  },
}

export const Error: Story = {
  args: {
    ...Default.args,
    value: 15,
    barClassName: "bg-error",
  },
}

export const Indeterminate: Story = {
  args: {
    ...Default.args,
    value: null,
    barClassName: "animate-pulse",
  },
}
