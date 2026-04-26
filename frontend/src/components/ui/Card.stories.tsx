import type { Meta, StoryObj } from "@storybook/react-vite"
import { Card } from "./Card"

const meta: Meta<typeof Card> = {
  title: "UI/Card",
  component: Card,
  tags: ["autodocs"],
  argTypes: {
    padding: {
      control: "select",
      options: ["none", "sm", "md", "lg"],
    },
    hoverable: {
      control: "boolean",
    },
  },
}

export default meta
type Story = StoryObj<typeof Card>

export const Default: Story = {
  args: {
    children: (
      <div className="flex flex-col gap-2">
        <h3 className="text-lg font-semibold">Card Title</h3>
        <p className="text-text-secondary">
          This is a standard card component with some content inside it.
        </p>
      </div>
    ),
    padding: "md",
    hoverable: false,
  },
}

export const Hoverable: Story = {
  args: {
    ...Default.args,
    hoverable: true,
  },
}

export const LargePadding: Story = {
  args: {
    ...Default.args,
    padding: "lg",
  },
}

export const NoPadding: Story = {
  args: {
    ...Default.args,
    padding: "none",
    children: (
      <div className="flex flex-col">
        <div className="bg-primary/10 p-4 border-b border-border-subtle">
          <h3 className="font-semibold">Full Width Header</h3>
        </div>
        <div className="p-4">
          <p>Content with manual padding inside a no-padding card.</p>
        </div>
      </div>
    ),
  },
}
