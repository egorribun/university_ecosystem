import type { Meta, StoryObj } from "@storybook/react"
import { Input } from "./Input"

const meta: Meta<typeof Input> = {
  title: "UI/Input",
  component: Input,
  tags: ["autodocs"],
  argTypes: {
    size: {
      control: "select",
      options: ["sm", "md", "lg"],
    },
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
type Story = StoryObj<typeof Input>

export const Default: Story = {
  args: {
    placeholder: "Enter text...",
    disabled: false,
    error: false,
    fullWidth: true,
  },
}

export const Small: Story = {
  args: {
    ...Default.args,
    size: "sm",
    placeholder: "Small input",
  },
}

export const Large: Story = {
  args: {
    ...Default.args,
    size: "lg",
    placeholder: "Large input",
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
    placeholder: "Disabled input",
  },
}

export const Password: Story = {
  args: {
    ...Default.args,
    type: "password",
    placeholder: "Password input",
  },
}
