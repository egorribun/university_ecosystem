import type { Meta, StoryObj } from "@storybook/react"
import { CardActionArea } from "./CardActionArea"
import { Card } from "./Card"

const meta: Meta<typeof CardActionArea> = {
  title: "UI/CardActionArea",
  component: CardActionArea,
  tags: ["autodocs"],
  argTypes: {
    disabled: {
      control: "boolean",
    },
  },
}

export default meta
type Story = StoryObj<typeof CardActionArea>

export const Default: Story = {
  render: (args) => (
    <div className="max-w-sm">
      <CardActionArea {...args}>
        <Card className="p-6">
          <h3 className="text-lg font-bold">Interactive Card</h3>
          <p className="text-text-secondary">Click or hover to see the animation effect.</p>
        </Card>
      </CardActionArea>
    </div>
  ),
  args: {
    disabled: false,
  },
}

export const Disabled: Story = {
  args: {
    disabled: true,
  },
  render: Default.render,
}
