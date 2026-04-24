import type { Meta, StoryObj } from "@storybook/react"
import { NotificationRelevanceScore } from "./NotificationRelevanceScore"

const meta: Meta<typeof NotificationRelevanceScore> = {
  title: "UI/NotificationRelevanceScore",
  component: NotificationRelevanceScore,
  tags: ["autodocs"],
  argTypes: {
    relevance: {
      control: "select",
      options: ["high", "medium", "low"],
    },
  },
}

export default meta
type Story = StoryObj<typeof NotificationRelevanceScore>

export const High: Story = {
  args: {
    relevance: "high",
  },
}

export const Medium: Story = {
  args: {
    relevance: "medium",
  },
}

export const Low: Story = {
  args: {
    relevance: "low",
  },
}
