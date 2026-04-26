import type { Meta, StoryObj } from "@storybook/react-vite"
import { useState } from "react"
import { Select } from "./Select"

const meta: Meta<typeof Select> = {
  title: "UI/Select",
  component: Select,
  tags: ["autodocs"],
  argTypes: {
    disabled: {
      control: "boolean",
    },
    error: {
      control: "boolean",
    },
  },
}

export default meta
type Story = StoryObj<typeof Select>

const options = [
  { value: "newest", label: "Newest First" },
  { value: "oldest", label: "Oldest First" },
  { value: "popular", label: "Most Popular" },
  { value: "trending", label: "Trending" },
]

export const Default: Story = {
  render: (args) => {
    const [value, setValue] = useState(args.value)
    return (
      <div className="w-72">
        <Select
          {...args}
          value={value}
          onValueChange={(val) => {
            setValue(val)
            args.onValueChange?.(val)
          }}
        />
      </div>
    )
  },
  args: {
    options,
    placeholder: "Sort by...",
    disabled: false,
    error: false,
  },
}

export const WithValue: Story = {
  args: {
    ...Default.args,
    value: "popular",
  },
  render: Default.render,
}

export const WithError: Story = {
  args: {
    ...Default.args,
    error: true,
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

export const LongList: Story = {
  args: {
    ...Default.args,
    options: Array.from({ length: 20 }, (_, i) => ({
      value: `option-${i}`,
      label: `Option ${i + 1}`,
    })),
  },
  render: Default.render,
}
