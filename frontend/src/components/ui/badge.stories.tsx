import type { Meta, StoryObj } from "@storybook/react-vite"
import { Badge } from "./badge"
import { Star, CheckCircle2, AlertCircle, Info } from "lucide-react"

const meta: Meta<typeof Badge> = {
  title: "UI/Badge",
  component: Badge,
  tags: ["autodocs"],
  argTypes: {
    tone: {
      control: "select",
      options: ["default", "primary", "success", "danger", "info"],
    },
    variant: {
      control: "select",
      options: ["solid", "outline"],
    },
    shape: {
      control: "select",
      options: ["pill", "circle"],
    },
    size: {
      control: "select",
      options: ["xs", "sm", "md"],
    },
  },
}

export default meta
type Story = StoryObj<typeof Badge>

export const Default: Story = {
  args: {
    label: "Draft",
    tone: "default",
  },
}

export const Primary: Story = {
  args: {
    label: "Featured",
    tone: "primary",
    leadingIcon: <Star size={12} />,
  },
}

export const Success: Story = {
  args: {
    label: "Confirmed",
    tone: "success",
    leadingIcon: <CheckCircle2 size={12} />,
  },
}

export const Danger: Story = {
  args: {
    label: "High Priority",
    tone: "danger",
    leadingIcon: <AlertCircle size={12} />,
  },
}

export const InfoTone: Story = {
  args: {
    label: "Note",
    tone: "info",
    leadingIcon: <Info size={12} />,
  },
}

export const Outline: Story = {
  args: {
    label: "Outline",
    variant: "outline",
  },
}

export const Circle: Story = {
  args: {
    children: "1",
    shape: "circle",
    tone: "primary",
    size: "sm",
  },
}
