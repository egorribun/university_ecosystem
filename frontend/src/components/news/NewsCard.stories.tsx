import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { Suspense } from "react"
import { LazyMotion, domAnimation } from "framer-motion"
import NewsCard, { type NewsCardProps } from "./NewsCard"

// Wave 198 SW1 — NewsCard Storybook fixture (CONTEXT-tier; ex-"A" card).
//
// The news/NewsCard LOGIC-WRAPPER (default export) — distinct from the dashboard
// NewsCard already storied under "Dashboard/NewsCard" (a different component; the
// basename collision masked this one as "covered"). Title "News/NewsCard".
//
// No module mocking needed: NewsCard passes `initialData` into useNewsInteraction,
// so prop values render immediately and a failed background refetch is silent under
// the preview QueryClient's retry:false. useBookmarks (localStorage/BroadcastChannel),
// IndexedDB, useSpotlight, useAuth, useLanguage, sanitizeNewsText (regex fallback)
// all work in real-browser Storybook; api.delete is click-only. It delegates to lazy
// NewsCardView WITHOUT its own Suspense, so the decorator supplies one.
//
// Variants: Default / Liked / LongTitle / DarkMode.

const BASE: NewsCardProps = {
  id: "news-1",
  title: "Университет запускает новую междисциплинарную лабораторию",
  title_en: "University Launches New Interdisciplinary Research Lab",
  content:
    "Новая лаборатория объединяет команды по data science, робототехнике и вычислительной биологии. Студенты получат доступ к современному оборудованию и совместным проектам с индустрией уже в этом семестре.",
  content_en:
    "The new facility hosts teams working across data science, robotics, and computational biology. Students get hands-on access to modern equipment and industry collaborations starting this semester.",
  created_at: "2026-05-20T09:00:00Z",
  image_url: "https://picsum.photos/seed/newscard/800/400",
  likes_count: 128,
  comments_count: 23,
  is_liked: false,
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div className="news-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
          <div style={{ width: 380 }}>
            <Suspense fallback={null}>
              <Story />
            </Suspense>
          </div>
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof NewsCard> = {
  title: "News/NewsCard",
  component: NewsCard,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
  args: { ...BASE },
}

export default meta
type Story = StoryObj<typeof NewsCard>

export const Default: Story = {
  decorators: [themed(false)],
}

export const Liked: Story = {
  args: { is_liked: true, likes_count: 129 },
  decorators: [themed(false)],
}

export const LongTitle: Story = {
  args: {
    title:
      "Международный симпозиум по передовым квантовым вычислениям и их практическому применению в современной криптографии и защищённых коммуникациях 2026",
  },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { is_liked: true, likes_count: 129 },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
