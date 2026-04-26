import type { Meta, StoryObj } from "@storybook/react-vite"
import { EventsHeader } from "./EventsHeader"
import { I18nextProvider } from "react-i18next"
import i18n from "@/i18n/config"

const meta = {
  title: "Features/Events/EventsHeader",
  component: EventsHeader,
  parameters: {
    layout: "padded",
  },
  decorators: [
    (Story) => (
      <I18nextProvider i18n={i18n}>
        <div className="max-w-4xl mx-auto mt-8">
          <Story />
        </div>
      </I18nextProvider>
    ),
  ],
  tags: ["autodocs"],
  argTypes: {
    onAddClick: { action: "onAddClick" },
    onSearchChange: { action: "onSearchChange" },
    onCategoryChange: { action: "onCategoryChange" },
    onSortChange: { action: "onSortChange" },
    onTabChange: { action: "onTabChange" },
    onDateRangeChange: { action: "onDateRangeChange" },
    onLocationChange: { action: "onLocationChange" },
  },
} satisfies Meta<typeof EventsHeader>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    isAdmin: false,
    eventsCount: 42,
    searchQuery: "",
    activeCategory: "all",
    sortMode: "newest",
    tab: "active",
    dateRange: {
      type: "all",
      start: null,
      end: null,
    },
    locationFilter: "all",
  },
}

export const AdminView: Story = {
  args: {
    ...Default.args,
    isAdmin: true,
  },
}

export const WithSearch: Story = {
  args: {
    ...Default.args,
    searchQuery: "hackathon",
  },
}

export const CategorySelected: Story = {
  args: {
    ...Default.args,
    activeCategory: "lecture",
  },
}

export const TabArchive: Story = {
  args: {
    ...Default.args,
    tab: "archive",
  },
}
