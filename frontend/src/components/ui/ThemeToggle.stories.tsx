import type { Meta, StoryObj } from "@storybook/react-vite"
import { useState } from "react"
import { ThemeToggle } from "./ThemeToggle"

const meta = {
  title: "UI/ThemeToggle",
  component: ThemeToggle,
  parameters: {
    layout: "centered",
    backgrounds: { default: "dark" },
  },
  tags: ["autodocs"],
} satisfies Meta<typeof ThemeToggle>

export default meta
type Story = StoryObj<typeof meta>

function ThemeToggleDemo({ size }: { size?: "sm" | "md" }) {
  const [isDark, setIsDark] = useState(true)
  return <ThemeToggle isDark={isDark} onToggle={() => setIsDark(!isDark)} size={size} />
}

const baseArgs = { isDark: true, onToggle: () => {} }

export const Default: Story = {
  args: baseArgs,
  render: () => <ThemeToggleDemo />,
}

export const Small: Story = {
  args: { ...baseArgs, size: "sm" as const },
  render: () => <ThemeToggleDemo size="sm" />,
}

export const LightMode: Story = {
  args: { ...baseArgs, isDark: false },
  render: () => {
    const [isDark, setIsDark] = useState(false)
    return <ThemeToggle isDark={isDark} onToggle={() => setIsDark(!isDark)} />
  },
}
