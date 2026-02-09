import type { Meta, StoryObj } from "@storybook/react-vite"
import { Skeleton } from "./skeleton"

const meta: Meta<typeof Skeleton> = {
  title: "UI/Skeleton",
  component: Skeleton,
  tags: ["autodocs"],
  argTypes: {
    width: {
      control: "text",
      description: "Width of the skeleton (number or string)",
    },
    height: {
      control: "text",
      description: "Height of the skeleton (number or string)",
    },
    rounded: {
      control: "select",
      options: [true, false, "50%", "9999px"],
      description: "Border radius (true for default, string for custom)",
    },
    ariaLabel: {
      control: "text",
      description: "Accessible label for screen readers",
    },
  },
  parameters: {
    backgrounds: {
      default: "dark",
    },
  },
}

export default meta
type Story = StoryObj<typeof Skeleton>

export const Default: Story = {
  args: {
    width: 200,
    height: 20,
    ariaLabel: "Loading content",
  },
}

export const TextLine: Story = {
  args: {
    width: "100%",
    height: 16,
    ariaLabel: "Loading text",
  },
}

export const Avatar: Story = {
  args: {
    width: 48,
    height: 48,
    rounded: "50%",
    ariaLabel: "Loading avatar",
  },
}

export const Button: Story = {
  args: {
    width: 120,
    height: 40,
    rounded: "9999px",
    ariaLabel: "Loading button",
  },
}

export const Card: Story = {
  args: {
    width: 320,
    height: 180,
    ariaLabel: "Loading card",
  },
}

export const MultipleLines: Story = {
  render: () => (
    <div className="flex flex-col gap-2" style={{ width: 300 }}>
      <Skeleton width="100%" height={16} ariaLabel="Loading line 1" />
      <Skeleton width="90%" height={16} ariaLabel="Loading line 2" />
      <Skeleton width="75%" height={16} ariaLabel="Loading line 3" />
    </div>
  ),
}




