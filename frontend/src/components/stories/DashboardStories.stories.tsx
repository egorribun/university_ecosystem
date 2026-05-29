import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import type { StoryItem } from "@/types/Story"
import DashboardStories from "./DashboardStories"

// Wave 199 SW1 — DashboardStories Storybook fixture (CONTEXT-tier, no infra).
//
// The dashboard "stories" carousel. Fully prop-driven (`stories: StoryItem[]`,
// `loading`); auto-advance only runs once a story is OPENED (openIndex state),
// so a static render = the circular thumbnail rail. No network on mount; only
// useMediaQuery is ambient. Full StoryItem (StoryOut) fixtures include the
// REQUIRED readonly `cover_url_optimized` field. Wrapped in `.dashboard-theme`
// to match the dashboard surface.
//
// Variants: Default (rail) / Loading (skeleton) / DarkMode.

const NOW = Date.now()
const H = 3_600_000
const D = 86_400_000

const buildStory = (n: number): StoryItem => ({
  id: `story-${n}`,
  title: `История ${n}`,
  title_en: `Story ${n}`,
  short_text: "Краткая заметка из жизни кампуса.",
  short_text_en: "A short blurb from campus life.",
  cover_url: `https://picsum.photos/seed/dash-story-${n}/240/360`,
  cta_url: null,
  published_at: new Date(NOW - n * H).toISOString(),
  expires_at: new Date(NOW + D).toISOString(),
  is_active: true,
  created_by: "admin-1",
  created_at: new Date(NOW - D).toISOString(),
  cover_url_optimized: null,
})

const STORIES: StoryItem[] = Array.from({ length: 6 }, (_, i) => buildStory(i + 1))

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div className="dashboard-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
          <div style={{ width: 760 }}>
            <Story />
          </div>
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof DashboardStories> = {
  title: "Dashboard/DashboardStories",
  component: DashboardStories,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
  args: { stories: STORIES, loading: false },
}

export default meta
type Story = StoryObj<typeof DashboardStories>

export const Default: Story = { decorators: [themed(false)] }

export const Loading: Story = {
  args: { stories: [], loading: true },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
