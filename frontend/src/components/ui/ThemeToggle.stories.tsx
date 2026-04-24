import type { Meta, StoryObj } from "@storybook/react"
import { useState } from "react"
import { ThemeToggle } from "./ThemeToggle"

const meta: Meta<typeof ThemeToggle> = {
  title: "UI/ThemeToggle",
  component: ThemeToggle,
  tags: ["autodocs"],
  argTypes: {
    isDark: {
      control: "boolean",
    },
    size: {
      control: "select",
      options: ["sm", "md"],
    },
  },
}

export default meta
type Story = StoryObj<typeof ThemeToggle>

export const Default: Story = {
  render: (args) => {
    const [isDark, setIsDark] = useState(args.isDark)
    return (
      <div className={isDark ? "dark" : ""}>
        <div className="bg-background p-8">
          <ThemeToggle {...args} isDark={isDark} onToggle={() => setIsDark(!isDark)} />
        </div>
      </div>
    )
  },
  args: {
    isDark: false,
    size: "md",
  },
}

export const Small: Story = {
  args: {
    ...Default.args,
    size: "sm",
  },
  render: Default.render,
}
