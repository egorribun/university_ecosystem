import type { Meta, StoryObj } from "@storybook/react"
import { useState } from "react"
import { ConfirmDialog } from "./ConfirmDialog"
import { Button } from "./Button"

const meta: Meta<typeof ConfirmDialog> = {
  title: "UI/ConfirmDialog",
  component: ConfirmDialog,
  tags: ["autodocs"],
  argTypes: {
    variant: {
      control: "select",
      options: ["default", "warning", "danger"],
    },
    open: {
      control: "boolean",
    },
    isLoading: {
      control: "boolean",
    },
  },
}

export default meta
type Story = StoryObj<typeof ConfirmDialog>

export const Default: Story = {
  render: (args) => {
    const [open, setOpen] = useState(args.open)
    return (
      <>
        <Button onClick={() => setOpen(true)}>Open Confirm Dialog</Button>
        <ConfirmDialog
          {...args}
          open={open}
          onCancel={() => setOpen(false)}
          onConfirm={() => {
            console.log("Confirmed")
            setOpen(false)
          }}
        />
      </>
    )
  },
  args: {
    open: false,
    title: "Delete Account",
    message: "Are you sure you want to delete your account? This action cannot be undone.",
    confirmText: "Delete",
    cancelText: "Cancel",
    variant: "danger",
    isLoading: false,
  },
}

export const Warning: Story = {
  args: {
    ...Default.args,
    variant: "warning",
    title: "Save Changes",
    message: "You have unsaved changes. Do you want to save them before leaving?",
    confirmText: "Save",
  },
  render: Default.render,
}

export const Loading: Story = {
  args: {
    ...Default.args,
    isLoading: true,
  },
  render: Default.render,
}
