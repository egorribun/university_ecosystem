import type { Meta, StoryObj } from "@storybook/react-vite-vite"
import DashboardSkeleton from "./DashboardSkeleton"

const meta: Meta<typeof DashboardSkeleton> = {
  title: "Dashboard/DashboardSkeleton",
  component: DashboardSkeleton,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof DashboardSkeleton>

export const Default: Story = {}
