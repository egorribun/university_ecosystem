import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { NewsQuickView } from "./NewsQuickView"

// Wave 196 SW4 — NewsQuickView Storybook fixture (CONTEXT-tier kickoff).
//
// Hover popover with an expanded news preview (category badge + date + title +
// extended preview + like/comment stats). Renders from props alone when `visible`
// is true; uses framer-motion `m.*` + AnimatePresence → LazyMotion. `.news-theme`
// supplies the NewsCategoryBadge tokens. The popover is `absolute`
// (pointer-events-none), so the decorator gives it a `relative` host;
// `position="bottom"` keeps it in view. `pauseAnimationAtEnd` freezes the entrance.
//
// Variants: Default (visible) / DarkMode.

const baseArgs = {
  visible: true,
  title: "University Launches New Interdisciplinary Research Lab",
  preview:
    "The new facility will host teams working across data science, robotics, and computational biology — opening to students next semester.",
  created_at: "2026-05-20T09:00:00Z",
  likesCount: 128,
  commentsCount: 23,
  category: "science" as const,
  position: "bottom" as const,
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div className="news-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
          <div style={{ position: "relative", width: 360, minHeight: 260 }}>
            <Story />
          </div>
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof NewsQuickView> = {
  title: "News/NewsQuickView",
  component: NewsQuickView,
  parameters: {
    layout: "centered",
    chromatic: { pauseAnimationAtEnd: true },
  },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof NewsQuickView>

export const Default: Story = {
  args: { ...baseArgs },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { ...baseArgs },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
