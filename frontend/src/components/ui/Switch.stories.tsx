import type { Meta, StoryObj } from "@storybook/react-vite"
import { useState } from "react"
import { Switch } from "./Switch"

const meta: Meta<typeof Switch> = {
  title: "UI/Switch",
  component: Switch,
  tags: ["autodocs"],
  argTypes: {
    checked: {
      control: "boolean",
    },
    disabled: {
      control: "boolean",
    },
  },
}

export default meta
type Story = StoryObj<typeof Switch>

export const Default: Story = {
  render: (args) => {
    const [checked, setChecked] = useState(args.checked ?? false)
    return (
      <div className="flex items-center gap-4">
        <Switch
          {...args}
          checked={checked}
          onCheckedChange={(val) => setChecked(val)}
        />
        <div className="flex flex-col">
          <span className="text-sm font-medium">Dark Mode</span>
          <span className="text-xs text-text-secondary">
            Enable or disable dark mode interface
          </span>
        </div>
      </div>
    )
  },
  args: {
    checked: false,
    disabled: false,
  },
}

export const Active: Story = {
  args: {
    ...Default.args,
    checked: true,
  },
  render: Default.render,
}

export const Disabled: Story = {
  args: {
    ...Default.args,
    disabled: true,
  },
  render: Default.render,
}

export const DisabledActive: Story = {
  args: {
    ...Default.args,
    disabled: true,
    checked: true,
  },
  render: Default.render,
}
