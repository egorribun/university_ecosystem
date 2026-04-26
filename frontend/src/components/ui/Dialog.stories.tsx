import type { Meta, StoryObj } from "@storybook/react-vite"
import { useState } from "react"
import { Dialog } from "./Dialog"
import { Button } from "./Button"
import { Input } from "./Input"

const meta: Meta<typeof Dialog> = {
  title: "UI/Dialog",
  component: Dialog,
  tags: ["autodocs"],
  argTypes: {
    size: {
      control: "select",
      options: ["sm", "md", "lg"],
    },
    open: {
      control: "boolean",
    },
    fullScreenOnMobile: {
      control: "boolean",
    },
  },
}

export default meta
type Story = StoryObj<typeof Dialog>

export const Default: Story = {
  render: (args) => {
    const [open, setOpen] = useState(args.open)
    return (
      <>
        <Button onClick={() => setOpen(true)}>Open Dialog</Button>
        <Dialog {...args} open={open} onClose={() => setOpen(false)}>
          <div className="space-y-4">
            <p>
              This is a standard dialog component. It uses a portal to render at the top level of
              the DOM and includes a focus trap for accessibility.
            </p>
            <Input placeholder="Focusable element inside" />
          </div>
        </Dialog>
      </>
    )
  },
  args: {
    open: false,
    title: "Dialog Title",
    subtitle: "A helpful description of the dialog purpose",
    size: "md",
    footer: (
      <>
        <Button variant="ghost">Cancel</Button>
        <Button variant="primary">Confirm Action</Button>
      </>
    ),
  },
}

export const Small: Story = {
  args: {
    ...Default.args,
    size: "sm",
    title: "Small Dialog",
  },
  render: Default.render,
}

export const Large: Story = {
  args: {
    ...Default.args,
    size: "lg",
    title: "Large Dialog",
  },
  render: Default.render,
}

export const NoFooter: Story = {
  args: {
    ...Default.args,
    footer: null,
  },
  render: Default.render,
}

export const FullScreenMobile: Story = {
  args: {
    ...Default.args,
    fullScreenOnMobile: true,
  },
  render: Default.render,
}
