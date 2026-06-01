import type { Meta, StoryObj } from "@storybook/react-vite"
import { NewsDetailSkeleton } from "./NewsDetailSkeleton"

// Self-contained: brings its own `.news-theme` wrapper + NewsBackdrop +
// min-h-screen, so no decorator is needed (only `layout: fullscreen`).
const meta: Meta<typeof NewsDetailSkeleton> = {
  title: "News/NewsDetailSkeleton",
  component: NewsDetailSkeleton,
  tags: ["autodocs"],
  parameters: { layout: "fullscreen" },
}

export default meta
type Story = StoryObj<typeof NewsDetailSkeleton>

export const Default: Story = { args: { isNarrow: false, prefersReducedMotion: false } }

export const Narrow: Story = { args: { isNarrow: true, prefersReducedMotion: false } }

export const ReducedMotion: Story = { args: { isNarrow: false, prefersReducedMotion: true } }
