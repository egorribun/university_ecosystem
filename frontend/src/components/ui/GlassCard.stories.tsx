import type { Meta, StoryObj } from "@storybook/react-vite"
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
}

export default meta
type Story = StoryObj<typeof GlassCard>

export const Default: Story = {
  args: {
    children: <div className="p-6 text-text-primary">Glass Card Content</div>,
    intensity: "medium",
    radius: "xl",
  },
}

export const LowIntensity: Story = {
  args: {
    children: <div className="p-6 text-text-primary">Low Intensity</div>,
    intensity: "low",
  },
}

export const HighIntensity: Story = {
  args: {
    children: <div className="p-6 text-text-primary">High Intensity</div>,
    intensity: "high",
  },
}

export const Elevated: Story = {
  args: {
    children: <div className="p-6 text-text-primary">Elevated</div>,
    intensity: "elevated",
  },
}

export const Interactive: Story = {
  args: {
    children: <div className="p-6 text-text-primary">Interactive Card</div>,
    interactive: true,
  },
}

export const Radii: Story = {
  render: () => (
    <div className="flex flex-col gap-4">
      <GlassCard radius="sm" className="p-4">Small Radius</GlassCard>
      <GlassCard radius="md" className="p-4">Medium Radius</GlassCard>
      <GlassCard radius="lg" className="p-4">Large Radius</GlassCard>
      <GlassCard radius="2xl" className="p-4">2XL Radius</GlassCard>
      <GlassCard radius="3xl" className="p-4">3XL Radius</GlassCard>
    </div>
  ),
}
