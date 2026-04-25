import type { Meta, StoryObj } from "@storybook/react"
import { useState } from "react"
import { Checkbox } from "./Checkbox"

const meta: Meta<typeof Checkbox> = {
  title: "UI/Checkbox",
  component: Checkbox,
  tags: ["autodocs"],
  argTypes: {
    checked: {
      control: "select",
      options: [true, false, "indeterminate"],
    },
    disabled: {
      control: "boolean",
    },
  },
}

export default meta
type Story = StoryObj<typeof Checkbox>

export const Default: Story = {
  render: (args) => {
    const [checked, setChecked] = useState(args.checked ?? false)
    return (
      <div className="flex items-center gap-3">
        <Checkbox
          {...args}
          checked={checked}
          onCheckedChange={(val) => setChecked(val)}
        />
        <span className="text-sm font-medium">Accept terms and conditions</span>
      </div>
    )
  },
  args: {
    checked: false,
    disabled: false,
  },
}

export const Checked: Story = {
  args: {
    ...Default.args,
    checked: true,
  },
  render: Default.render,
}

export const Indeterminate: Story = {
  args: {
    ...Default.args,
    checked: "indeterminate",
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

export const DisabledChecked: Story = {
  args: {
    ...Default.args,
    disabled: true,
    checked: true,
  },
  render: Default.render,
}
