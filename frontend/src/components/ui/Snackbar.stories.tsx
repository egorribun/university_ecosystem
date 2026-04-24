import type { Meta, StoryObj } from "@storybook/react"
import { useState } from "react"
import Snackbar from "./Snackbar"
import { Button } from "./Button"

const meta: Meta<typeof Snackbar> = {
  title: "UI/Snackbar",
  component: Snackbar,
  tags: ["autodocs"],
  argTypes: {
    open: {
      control: "boolean",
    },
    duration: {
      control: "number",
    },
  },
}

export default meta
type Story = StoryObj<typeof Snackbar>

export const Default: Story = {
  render: (args) => {
    const [open, setOpen] = useState(args.open)
    return (
      <>
        <Button onClick={() => setOpen(true)}>Show Snackbar</Button>
        <Snackbar {...args} open={open} onClose={() => setOpen(false)} />
      </>
    )
  },
  args: {
    open: false,
    message: "Action completed successfully",
    duration: 3000,
  },
}

export const LongMessage: Story = {
  args: {
    ...Default.args,
    message: "This is a much longer message to see how it handles multi-line text if needed.",
  },
  render: Default.render,
}
