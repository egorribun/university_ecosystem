import type { Meta, StoryObj } from "@storybook/react-vite"
import EventCard from "./EventCard"

const meta: Meta<typeof EventCard> = {
  title: "Components/EventCard",
  component: EventCard,
  tags: ["autodocs"],
  parameters: {
    layout: "centered",
  },
}

export default meta
type Story = StoryObj<typeof EventCard>

const mockEvent = {
  id: "uuid-1",
  title: "Modern Web Development Workshop",
  title_en: "Modern Web Development Workshop",
  description: "Join us for an intensive workshop on React 19, Vite, and tailwind CSS.",
  description_en: "Join us for an intensive workshop on React 19, Vite, and tailwind CSS.",
  event_type: "Workshop",
  event_type_en: "Workshop",
  location: "Computer Lab 404",
  location_en: "Computer Lab 404",
  starts_at: new Date().toISOString(),
  ends_at: new Date(Date.now() + 7200000).toISOString(),
  created_by: "uuid-1",
  speaker: "Dr. Jane Smith",
  photo_url:
    "https://images.unsplash.com/photo-1540575467063-178a50c2df87?w=800&auto=format&fit=crop",
  attendance_count: 42,
  max_attendance: 100,
}

export const Default: Story = {
  args: {
    ...mockEvent,
  },
}

export const Upcoming: Story = {
  args: {
    ...mockEvent,
    starts_at: new Date(Date.now() + 86400000).toISOString(),
    ends_at: new Date(Date.now() + 86400000 + 3600000).toISOString(),
  },
}

export const Past: Story = {
  args: {
    ...mockEvent,
    starts_at: new Date(Date.now() - 172800000).toISOString(),
    ends_at: new Date(Date.now() - 172800000 + 3600000).toISOString(),
  },
}

export const WithoutImage: Story = {
  args: {
    ...mockEvent,
    image_url: undefined,
  },
}

export const LongTitle: Story = {
  args: {
    ...mockEvent,
    title:
      "International Symposium on Advanced Quantum Computing and Its Practical Applications in Modern Cryptography and Secure Communications 2025",
  },
}
