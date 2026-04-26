import type { Meta, StoryObj } from "@storybook/react-vite"
import { EmptyState } from "./EmptyState"
import { Search, Calendar, Inbox, Plus } from "lucide-react"
import { Button } from "./Button"

const meta: Meta<typeof EmptyState> = {
  title: "UI/EmptyState",
  component: EmptyState,
  tags: ["autodocs"],
  argTypes: {
    titleAs: {
      control: "select",
      options: ["h2", "h3", "h4"],
    },
  },
}

export default meta
type Story = StoryObj<typeof EmptyState>

export const Default: Story = {
  args: {
    icon: <Inbox className="h-8 w-8" />,
    title: "No data available",
    description: "There's nothing to show here yet. Check back later!",
  },
}

export const SearchResults: Story = {
  args: {
    icon: <Search className="h-8 w-8" />,
    title: "No matches found",
    description: "Try adjusting your search filters to find what you're looking for.",
    action: <Button variant="outline">Clear Filters</Button>,
  },
}

export const Events: Story = {
  args: {
    icon: <Calendar className="h-8 w-8" />,
    title: "No upcoming events",
    description: "Be the first to create one and invite your colleagues.",
    action: (
      <Button variant="primary">
        <Plus className="mr-2 h-4 w-4" />
        Create Event
      </Button>
    ),
  },
}

export const Simple: Story = {
  args: {
    title: "Nothing here",
  },
}
