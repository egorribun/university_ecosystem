import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import type { NewsItem } from "@/api/news"
import { NewsCardList } from "./NewsCardList"

// Wave 198 SW6 — NewsCardList Storybook fixture (dashboard, pure-props).
//
// Compact dashboard news list (DateBullet + title + snippet, useNavigate on click).
// `news: NewsItem[]` (= NewsOut — needs the readonly image_url_optimized). Loading
// → skeleton rows; empty → empty text. No m.*; dashboard matte tokens are global
// (dashboard-theme.css was deleted in W119), so a plain .dark/bg-page decorator suffices.
//
// Variants: Default / Loading / Empty / DarkMode.

const NEWS: NewsItem[] = [
  {
    id: "n1",
    title: "New interdisciplinary research lab opens",
    content:
      "The new facility hosts teams across data science, robotics, and computational biology for the spring term.",
    created_at: "2026-05-28T09:00:00Z",
    image_url_optimized: null,
  },
  {
    id: "n2",
    title: "Spring semester schedule published",
    content: "Check the updated timetable for all faculties — exam dates included.",
    created_at: "2026-05-26T12:00:00Z",
    image_url_optimized: null,
  },
  {
    id: "n3",
    title: "Hackathon 2026 registration open",
    content: "Sign up for the annual 48-hour coding marathon before June 1.",
    created_at: "2026-05-24T15:00:00Z",
    image_url_optimized: null,
  },
]

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div style={{ width: 420 }}>
          <Story />
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof NewsCardList> = {
  title: "Dashboard/NewsCardList",
  component: NewsCardList,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
  args: { news: NEWS, loading: false, locale: "en" },
}

export default meta
type Story = StoryObj<typeof NewsCardList>

export const Default: Story = {
  decorators: [themed(false)],
}

export const Loading: Story = {
  args: { loading: true },
  decorators: [themed(false)],
}

export const Empty: Story = {
  args: { news: [] },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
