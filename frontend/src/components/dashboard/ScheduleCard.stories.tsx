import type { Meta, StoryObj } from "@storybook/react-vite-vite"
import { ScheduleCard } from "./ScheduleCard"

const meta: Meta<typeof ScheduleCard> = {
  title: "Dashboard/ScheduleCard",
  component: ScheduleCard,
  tags: ["autodocs"],
  parameters: {
    layout: "centered",
  },
  decorators: [
    (Story) => (
      <div style={{ width: "400px" }}>
        <Story />
      </div>
    ),
  ],
}

export default meta
type Story = StoryObj<typeof ScheduleCard>

export const Student: Story = {
  args: {
    userRole: "student",
    userGroupId: 101,
    time: new Date("2026-12-01T10:00:00Z"),
  },
}

export const Teacher: Story = {
  args: {
    userRole: "teacher",
    time: new Date("2026-12-01T10:00:00Z"),
  },
}

export const Empty: Story = {
  args: {
    userRole: "student",
    userGroupId: 999, // Assuming no data for this group
    time: new Date("2026-12-01T10:00:00Z"),
  },
}

export const Loading: Story = {
  args: {
    userRole: "student",
    userGroupId: 101,
    time: new Date("2026-12-01T10:00:00Z"),
  },
  parameters: {
    // We can't easily force isLoading state here without mocking useDashboardSchedule
    // but in Storybook we usually mock at the MSW level if setup.
  },
}
