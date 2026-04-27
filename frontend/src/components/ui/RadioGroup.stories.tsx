import type { Meta, StoryObj } from "@storybook/react-vite"
import { useState } from "react"
import { RadioGroup, RadioGroupItem } from "./RadioGroup"

const meta: Meta<typeof RadioGroup> = {
  title: "UI/RadioGroup",
  component: RadioGroup,
  tags: ["autodocs"],
  argTypes: {
    disabled: {
      control: "boolean",
    },
    row: {
      control: "boolean",
    },
  },
}

export default meta
type Story = StoryObj<typeof RadioGroup>

export const Default: Story = {
  render: (args) => {
    const [value, setValue] = useState("option-1")
    return (
      <RadioGroup
        {...args}
        value={value}
        onChange={(_, val) => {
          setValue(val)
          args.onChange?.(_, val)
        }}
      >
        <div className="flex items-center gap-2">
          <RadioGroupItem value="option-1" id="r1" />
          <label htmlFor="r1" className="cursor-pointer text-sm font-medium text-text-primary">
            Option One
          </label>
        </div>
        <div className="flex items-center gap-2">
          <RadioGroupItem value="option-2" id="r2" />
          <label htmlFor="r2" className="cursor-pointer text-sm font-medium text-text-primary">
            Option Two
          </label>
        </div>
        <div className="flex items-center gap-2">
          <RadioGroupItem value="option-3" id="r3" />
          <label htmlFor="r3" className="cursor-pointer text-sm font-medium text-text-primary">
            Option Three
          </label>
        </div>
      </RadioGroup>
    )
  },
  args: {
    row: false,
    disabled: false,
  },
}

export const Row: Story = {
  args: {
    ...Default.args,
    row: true,
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
