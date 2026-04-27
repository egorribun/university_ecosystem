import type { Meta, StoryObj } from "@storybook/react-vite"
import { Textarea } from "./Textarea"

const meta: Meta<typeof Textarea> = {
  title: "UI/Textarea",
  component: Textarea,
  tags: ["autodocs"],
  argTypes: {
    error: {
      control: "boolean",
    },
    fullWidth: {
      control: "boolean",
    },
    disabled: {
      control: "boolean",
    },
  },
}

export default meta
type Story = StoryObj<typeof Textarea>

export const Default: Story = {
  args: {
    placeholder: "Enter your message...",
    disabled: false,
    error: false,
    fullWidth: true,
    rows: 4,
  },
}

export const WithError: Story = {
  args: {
    ...Default.args,
    error: true,
    placeholder: "Error state",
  },
}

export const Disabled: Story = {
  args: {
    ...Default.args,
    disabled: true,
    placeholder: "Disabled textarea",
  },
}

export const FixedHeight: Story = {
  args: {
    ...Default.args,
    className: "h-64 resize-none",
    placeholder: "Non-resizable large textarea",
  },
}
