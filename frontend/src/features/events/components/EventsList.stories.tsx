import type { Meta, StoryObj } from "@storybook/react-vite-vite"
import { EventsList } from "./EventsList"
import type { Event } from "@/types/Event"

const mockEvents: Event[] = [
  {
    id: "1",
    title: "University Festival 2024",
    description: "The biggest event of the year with music, food, and games.",
    start_date: "2024-12-30T10:00:00Z",
    end_date: "2024-12-30T22:00:00Z",
    location: "Main Square",
    image_url:
      "https://images.unsplash.com/photo-1533174072545-7a4b6ad7a6c3?w=800&auto=format&fit=crop&q=60",
    registered_count: 450,
    organizer_id: "5",
    organizer: {
      id: "5",
      full_name: "Events Committee",
      avatar_url: "",
    },
  },
  {
    id: "2",
    title: "Career Fair",
    description: "Meet representatives from top companies.",
    start_date: "2024-12-31T09:00:00Z",
    end_date: "2024-12-31T17:00:00Z",
    location: "Hall B",
    image_url:
      "https://images.unsplash.com/photo-1511578314322-379afb476865?w=800&auto=format&fit=crop&q=60",
    registered_count: 120,
    organizer_id: "3",
    organizer: {
      id: "3",
      full_name: "Career Center",
      avatar_url: "",
    },
  },
]

const meta: Meta<typeof EventsList> = {
  title: "Features/Events/EventsList",
  component: EventsList,
  parameters: {
    layout: "fullscreen",
  },
  decorators: [
    (Story) => (
      <div className="p-4 sm:p-8 bg-background min-h-screen">
        <Story />
      </div>
    ),
  ],
}

export default meta
type Story = StoryObj<typeof EventsList>

export const Default: Story = {
  args: {
    eventsList: mockEvents,
    isInitialLoading: false,
    isFetching: false,
    isFetchingNextPage: false,
    hasNextPage: false,
    fetchNextPage: () => {},
    refreshEvents: () => {},
    onAddClick: () => {},
    isAdmin: false,
    isOnline: true,
    tab: "active",
    onTabChange: () => {},
  },
}

export const Loading: Story = {
  args: {
    ...Default.args,
    eventsList: [],
    isInitialLoading: true,
  },
}

export const Empty: Story = {
  args: {
    ...Default.args,
    eventsList: [],
  },
}

export const Offline: Story = {
  args: {
    ...Default.args,
    eventsList: [],
    isOnline: false,
  },
}

export const FetchingNextPage: Story = {
  args: {
    ...Default.args,
    isFetchingNextPage: true,
    hasNextPage: true,
  },
}
