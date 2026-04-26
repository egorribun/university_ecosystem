import type { Meta, StoryObj } from "@storybook/react-vite-vite"
import { Button } from "./Button"
import { Mail, ArrowRight } from "lucide-react"

const meta: Meta<typeof Button> = {
  title: "UI/Button",
  component: Button,
  tags: ["autodocs"],
  argTypes: {
    variant: {
      control: "select",
      options: ["solid", "outline", "ghost"],
    },
    size: {
      control: "select",
      options: ["sm", "md", "lg"],
    },
    fullWidth: {
      control: "boolean",
    },
    loading: {
      control: "boolean",
    },
    disabled: {
      control: "boolean",
    },
  },
}

export default meta
type Story = StoryObj<typeof Button>

export const Solid: Story = {
  args: {
    children: "Solid Button",
    variant: "solid",
    size: "md",
  },
}

export const Outline: Story = {
  args: {
    children: "Outline Button",
    variant: "outline",
    size: "md",
  },
}

export const Ghost: Story = {
  args: {
    children: "Ghost Button",
    variant: "ghost",
    size: "md",
  },
}

export const WithIcons: Story = {
  args: {
    children: "Send Message",
    leadingIcon: <Mail size={18} />,
    trailingIcon: <ArrowRight size={18} />,
  },
}

export const Loading: Story = {
  args: {
    children: "Saving Changes",
    loading: true,
  },
}

export const FullWidth: Story = {
  args: {
    children: "Full Width Button",
    fullWidth: true,
  },
}
