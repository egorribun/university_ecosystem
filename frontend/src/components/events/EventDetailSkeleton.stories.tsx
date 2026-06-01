import type { Meta, StoryObj } from "@storybook/react-vite"
import { EventDetailSkeleton } from "./EventDetailSkeleton"

// Self-contained: brings its own `.events-theme` wrapper + EventsBackdrop +
// min-h-screen, so no decorator is needed (only `layout: fullscreen`).
const meta: Meta<typeof EventDetailSkeleton> = {
  title: "Events/EventDetailSkeleton",
  component: EventDetailSkeleton,
  tags: ["autodocs"],
  parameters: { layout: "fullscreen" },
}

export default meta
type Story = StoryObj<typeof EventDetailSkeleton>

export const Default: Story = { args: { isNarrow: false, prefersReducedMotion: false } }

export const Narrow: Story = { args: { isNarrow: true, prefersReducedMotion: false } }

export const ReducedMotion: Story = { args: { isNarrow: false, prefersReducedMotion: true } }
