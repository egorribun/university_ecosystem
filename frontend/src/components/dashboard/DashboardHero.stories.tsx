import type { Meta, StoryObj } from "@storybook/react-vite-vite"
import { DashboardHero } from "./DashboardHero"
import type { User } from "@/types/User"

const mockUser: User = {
  id: 1,
  email: "john.doe@university.edu",
  full_name: "John Doe",
  role: "student",
  avatar_url:
    "https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=100&auto=format&fit=crop&q=60",
  mfa_enabled: true,
}

const meta: Meta<typeof DashboardHero> = {
  title: "Dashboard/DashboardHero",
  component: DashboardHero,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof DashboardHero>

const baseArgs = {
  user: mockUser,
  time: new Date(),
  hh: "12",
  mm: "45",
  dateStr: "Friday, 24 April",
  isNarrow: false,
  prefersReducedMotion: false,
}

export const Default: Story = {
  args: baseArgs,
}

export const Morning: Story = {
  args: {
    ...baseArgs,
    time: new Date(2024, 3, 24, 8, 0, 0),
    hh: "08",
    mm: "00",
    dateStr: "Wednesday, 24 April",
  },
}

export const Evening: Story = {
  args: {
    ...baseArgs,
    time: new Date(2024, 3, 24, 20, 0, 0),
    hh: "20",
    mm: "00",
    dateStr: "Wednesday, 24 April",
  },
}

export const Anonymous: Story = {
  args: {
    ...baseArgs,
    user: null,
  },
}

export const Narrow: Story = {
  args: {
    ...baseArgs,
    isNarrow: true,
  },
}

export const WithStories: Story = {
  args: {
    ...baseArgs,
    storiesSlot: (
      <div className="flex gap-4 p-2 bg-white/5 rounded-2xl overflow-x-auto">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="flex-shrink-0 w-16 h-16 rounded-full border-2 border-brand p-0.5">
            <div className="w-full h-full rounded-full bg-glass-bg border border-glass-border flex items-center justify-center text-xs font-bold">
              #{i}
            </div>
          </div>
        ))}
      </div>
    ),
  },
}
