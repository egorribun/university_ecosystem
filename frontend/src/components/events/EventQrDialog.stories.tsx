import type { Meta, StoryObj } from "@storybook/react-vite"
import { EventQrDialog } from "./EventQrDialog"

// Dialog portals to document.body (outside the story decorator), so a `.dark`
// wrapper decorator can't theme it — Open is shown in the default theme only.
const meta: Meta<typeof EventQrDialog> = {
  title: "Events/EventQrDialog",
  component: EventQrDialog,
  tags: ["autodocs"],
  parameters: {
    layout: "fullscreen",
    // Loading spinner animates while the QR image fetches — freeze for Chromatic.
    chromatic: { pauseAnimationAtEnd: true },
  },
}

export default meta
type Story = StoryObj<typeof EventQrDialog>

export const Open: Story = {
  args: {
    open: true,
    onClose: () => {},
    qr: "https://guu.ru/events/ai-symposium-2026",
  },
  parameters: {
    docs: {
      description: {
        story: "QR check-in dialog; the QR image is fetched from a remote generator.",
      },
    },
  },
}
