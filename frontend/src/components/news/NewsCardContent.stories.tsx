import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import NewsCardContent from "./NewsCardContent"

// Wave 196 SW4 — NewsCardContent Storybook fixture (CONTEXT-tier kickoff).
//
// Text-content section of a news card (title-as-Link, preview, like / comment /
// reading-time / bookmark footer + hover CTA). Renders from primitive props +
// callbacks + the global decorators alone: the title `<Link to="/news/$id">`
// resolves via preview.tsx's RouterProvider, labels via I18nextProvider. No theme
// scope beyond globals; no framer-motion (CSS like-celebration). The `before:absolute`
// title overlay needs a `relative group` host (provided by the decorator).
//
// Variants: Default / Liked / Bookmarked / DarkMode.

const baseArgs = {
  id: "n1",
  title: "University Launches New Interdisciplinary Research Lab",
  preview:
    "The new facility will host teams working across data science, robotics, and computational biology.",
  isLiked: false,
  likesCount: 128,
  commentsCount: 23,
  readingTime: 5,
  onToggleLike: () => {},
  hoveringDisabled: false,
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div className="news-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div
          className="group relative overflow-hidden rounded-2xl border border-glass-border bg-surface shadow-sm"
          style={{ width: 360 }}
        >
          <Story />
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof NewsCardContent> = {
  title: "News/NewsCardContent",
  component: NewsCardContent,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof NewsCardContent>

export const Default: Story = {
  args: { ...baseArgs },
  decorators: [themed(false)],
}

export const Liked: Story = {
  args: { ...baseArgs, isLiked: true, likesCount: 129 },
  decorators: [themed(false)],
}

export const Bookmarked: Story = {
  args: { ...baseArgs, isBookmarked: true, onToggleBookmark: () => {} },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { ...baseArgs, isLiked: true, isBookmarked: true, onToggleBookmark: () => {} },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
