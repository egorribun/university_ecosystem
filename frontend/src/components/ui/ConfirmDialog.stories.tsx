import type { Meta, StoryObj } from "@storybook/react-vite"
import { useState } from "react"
import { ConfirmDialog } from "./ConfirmDialog"

const meta = {
  title: "UI/ConfirmDialog",
  component: ConfirmDialog,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof ConfirmDialog>

export default meta
type Story = StoryObj<typeof meta>

function ConfirmDialogDemo({ variant }: { variant?: "danger" | "warning" | "default" }) {
  const [open, setOpen] = useState(true)
  return (
    <>
      <button onClick={() => setOpen(true)}>Open Dialog</button>
      <ConfirmDialog
        open={open}
        title="Confirm Action"
        message="Are you sure you want to proceed? This action cannot be undone."
        confirmText="Confirm"
        cancelText="Cancel"
        variant={variant}
        onConfirm={() => setOpen(false)}
        onCancel={() => setOpen(false)}
      />
    </>
  )
}

const baseArgs = {
  open: true,
  title: "Confirm Action",
  message: "Are you sure you want to proceed?",
  confirmText: "Confirm",
  cancelText: "Cancel",
  onConfirm: () => {},
  onCancel: () => {},
}

export const Default: Story = {
  args: baseArgs,
  render: () => <ConfirmDialogDemo />,
}

export const Danger: Story = {
  args: { ...baseArgs, variant: "danger" as const },
  render: () => <ConfirmDialogDemo variant="danger" />,
}

export const Warning: Story = {
  args: { ...baseArgs, variant: "warning" as const },
  render: () => <ConfirmDialogDemo variant="warning" />,
}
