import type { Meta, StoryObj } from "@storybook/react-vite-vite"
import { EventCardSkeleton } from "@/components/events/EventCard/EventCardSkeleton"
import NewsCardSkeleton from "./NewsCardSkeleton"
import { ProfileCardSkeleton } from "./ProfileCardSkeleton"
import { ScheduleCardSkeleton } from "./ScheduleCardSkeleton"

const meta: Meta = {
  title: "Components/Skeletons",
  tags: ["autodocs"],
  parameters: {
    layout: "padded",
    backgrounds: {
      default: "dark",
    },
  },
}

export default meta

export const EventCard: StoryObj = {
  render: () => <EventCardSkeleton />,
  parameters: {
    docs: {
      description: {
        story:
          "Loading skeleton for event cards with image, title, date, location, and action button placeholders.",
      },
    },
  },
}

export const NewsCard: StoryObj = {
  render: () => <NewsCardSkeleton />,
  parameters: {
    docs: {
      description: {
        story: "Loading skeleton for news cards with image and content area placeholders.",
      },
    },
  },
}

export const ProfileCard: StoryObj = {
  render: () => <ProfileCardSkeleton />,
  parameters: {
    docs: {
      description: {
        story: "Loading skeleton for profile cards with avatar, name, and stats placeholders.",
      },
    },
  },
}

export const ScheduleCard: StoryObj = {
  render: () => <ScheduleCardSkeleton />,
  parameters: {
    docs: {
      description: {
        story:
          "Loading skeleton for schedule cards with time slots and lesson details placeholders.",
      },
    },
  },
}

export const EventCardGrid: StoryObj = {
  render: () => (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <EventCardSkeleton />
      <EventCardSkeleton />
      <EventCardSkeleton />
    </div>
  ),
  parameters: {
    docs: {
      description: {
        story: "Multiple EventCard skeletons in a responsive grid layout.",
      },
    },
  },
}

export const NewsCardList: StoryObj = {
  render: () => (
    <div className="flex flex-col gap-4 max-w-[36rem]">
      <NewsCardSkeleton />
      <NewsCardSkeleton />
    </div>
  ),
  parameters: {
    docs: {
      description: {
        story: "Multiple NewsCard skeletons in a vertical list layout.",
      },
    },
  },
}
