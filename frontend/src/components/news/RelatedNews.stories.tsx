import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import type { NewsItem } from "@/api/news"
import { RelatedNews } from "./RelatedNews"

// Wave 197 SW1 — RelatedNews Storybook fixture (CONTEXT-tier, cheap/ambient).
//
// 3-column grid of related articles. Takes an `items: NewsItem[]` prop directly
// (no internal useQuery — the upstream page hook reads the cache; the component is
// pure), so a story passes a fixture array. Each card is a TanStack
// <Link to="/news/$id"> (resolves in preview.tsx's root-only router) with
// SmartImage + an inferred NewsCategoryBadge + a Moscow-formatted date. Returns
// null when items is empty.
//
// Variants: Default (3 items, last image-less → gradient fallback) / DarkMode.

const RELATED: NewsItem[] = [
  {
    id: "n1",
    title: "Новая исследовательская лаборатория",
    title_en: "New Interdisciplinary Research Lab",
    content: "Data science, robotics, and computational biology teams under one roof.",
    created_at: "2026-05-20T09:00:00Z",
    image_url: "https://picsum.photos/seed/related-n1/400/300",
    image_url_optimized: null,
  },
  {
    id: "n2",
    title: "Студенческий хакатон 2026",
    title_en: "Student Hackathon 2026",
    content: "Forty-eight hours of building across twelve interdisciplinary teams.",
    created_at: "2026-05-18T12:00:00Z",
    image_url: "https://picsum.photos/seed/related-n2/400/300",
    image_url_optimized: null,
  },
  {
    id: "n3",
    title: "Обновление кампусной библиотеки",
    title_en: "Campus Library Renovation",
    content: "Expanded study spaces and a new digital archive open this term.",
    created_at: "2026-05-15T08:30:00Z",
    image_url: null,
    image_url_optimized: null,
  },
]

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div className="news-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <div style={{ maxWidth: 880, margin: "0 auto" }}>
          <Story />
        </div>
      </div>
    </div>
  )
}

const meta: Meta<typeof RelatedNews> = {
  title: "News/RelatedNews",
  component: RelatedNews,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof RelatedNews>

export const Default: Story = {
  args: { items: RELATED },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { items: RELATED },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
