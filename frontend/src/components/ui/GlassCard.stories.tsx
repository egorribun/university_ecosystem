import type { Meta, StoryObj } from "@storybook/react"
import { GlassCard } from "./GlassCard"

const meta: Meta<typeof GlassCard> = {
  title: "UI/GlassCard",
  component: GlassCard,
  tags: ["autodocs"],
  argTypes: {
    intensity: {
      control: "select",
      options: ["low", "medium", "high", "elevated"],
    },
    radius: {
      control: "select",
      options: ["none", "sm", "md", "lg", "xl", "2xl", "3xl"],
    },
    interactive: {
      control: "boolean",
    },
  },
  parameters: {
    backgrounds: {
      default: "dark",
    },
  },
}

export default meta
type Story = StoryObj<typeof GlassCard>

export const Default: Story = {
  args: {
    children: (
      <div className="p-8">
        <h3 className="mb-2 text-xl font-bold text-text-primary">Glassmorphism Card</h3>
        <p className="text-text-secondary">
          A premium card component with backdrop blur and noise texture.
        </p>
      </div>
    ),
    intensity: "medium",
    radius: "xl",
    interactive: false,
  },
}

export const LowIntensity: Story = {
  args: {
    ...Default.args,
    intensity: "low",
  },
}

export const HighIntensity: Story = {
  args: {
    ...Default.args,
    intensity: "high",
  },
}

export const Elevated: Story = {
  args: {
    ...Default.args,
    intensity: "elevated",
  },
}

export const Interactive: Story = {
  args: {
    ...Default.args,
    interactive: true,
  },
}
