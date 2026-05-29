import type { Decorator, Meta, StoryObj } from "@storybook/react-vite"
import { NewsDetailHeader } from "./NewsDetailHeader"

const noop = () => {}

const baseArgs = {
  displayTitle: "University Announces New AI Research Center",
  createdAt: "2026-05-20T09:00:00Z",
  createdAtIso: "2026-05-20T09:00:00.000Z",
  createdAtLabel: "20 MAY 2026",
  readingTimeMinutes: 5,
  isLiked: false,
  likesCount: 42,
  bookmarked: false,
  isAdmin: false,
  saving: false,
  deleting: false,
  sharing: false,
  onShare: noop,
  onToggleLike: noop,
  onToggleBookmark: noop,
  onEditOpen: noop,
  onDeleteOpen: noop,
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div className="news-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div style={{ maxWidth: 768, margin: "0 auto" }}>
          <Story />
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof NewsDetailHeader> = {
  title: "News/NewsDetailHeader",
  component: NewsDetailHeader,
  tags: ["autodocs"],
  parameters: { layout: "fullscreen" },
}

export default meta
type Story = StoryObj<typeof NewsDetailHeader>

export const Default: Story = { args: baseArgs, decorators: [themed(false)] }

export const Liked: Story = {
  args: { ...baseArgs, isLiked: true, likesCount: 43 },
  decorators: [themed(false)],
}

export const Bookmarked: Story = {
  args: { ...baseArgs, bookmarked: true },
  decorators: [themed(false)],
}

export const Admin: Story = {
  args: { ...baseArgs, isAdmin: true },
  decorators: [themed(false)],
  parameters: { docs: { description: { story: "Admin view adds Edit + Delete icon buttons." } } },
}

export const DarkMode: Story = {
  args: baseArgs,
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
