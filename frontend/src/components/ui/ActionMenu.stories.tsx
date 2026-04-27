import type { Meta, StoryObj } from "@storybook/react-vite"
import { ActionMenu } from "./ActionMenu"
import { Edit, Trash, Share, Copy } from "lucide-react"

const meta: Meta<typeof ActionMenu> = {
  title: "UI/ActionMenu",
  component: ActionMenu,
  tags: ["autodocs"],
  argTypes: {
    placement: {
      control: "select",
      options: ["bottom-end", "bottom-start"],
    },
  },
}

export default meta
type Story = StoryObj<typeof ActionMenu>

const items = [
  { label: "Edit", icon: <Edit size={16} />, onClick: () => console.warn("Edit") },
  { label: "Copy", icon: <Copy size={16} />, onClick: () => console.warn("Copy") },
  { label: "Share", icon: <Share size={16} />, onClick: () => console.warn("Share") },
  {
    label: "Delete",
    icon: <Trash size={16} />,
    onClick: () => console.warn("Delete"),
    variant: "danger" as const,
  },
]

export const Default: Story = {
  args: {
    items,
  },
}

export const CustomTrigger: Story = {
  args: {
    items,
    trigger: <span className="text-sm font-medium">Actions</span>,
    triggerClassName: "w-auto h-auto px-3 py-1.5 rounded-md border border-subtle",
  },
}

export const BottomStart: Story = {
  args: {
    items,
    placement: "bottom-start",
  },
}

export const WithDisabledItems: Story = {
  args: {
    items: [
      ...items,
      { label: "Archive", icon: <Share size={16} />, onClick: () => {}, disabled: true },
    ],
  },
}
