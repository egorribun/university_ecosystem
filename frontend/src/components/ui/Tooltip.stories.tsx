import type { Meta, StoryObj } from "@storybook/react-vite"
import { Tooltip } from "./Tooltip"
import { Info } from "lucide-react"

const meta: Meta<typeof Tooltip> = {
  title: "UI/Tooltip",
  component: Tooltip,
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof Tooltip>

export const Default: Story = {
  args: {
    content: "This is a helpful tooltip message",
    children: (
      <button className="flex items-center gap-2 rounded-md bg-glass-bg p-2 text-text-primary border border-subtle">
        <Info size={16} />
        Hover me
      </button>
    ),
  },
}

export const RichContent: Story = {
  args: {
    content: (
      <span>
        Detailed <strong>rich text</strong> explaining something complex.
      </span>
    ),
    children: (
      <button className="flex items-center gap-2 rounded-md bg-glass-bg p-2 text-text-primary border border-subtle">
        <Info size={16} />
        Rich Tooltip (SR only)
      </button>
    ),
  },
}
