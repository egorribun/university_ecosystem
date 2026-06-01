import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { useSpotlight } from "@/components/ui/Spotlight"
import { NewsCardView, type NewsCardViewProps } from "./NewsCardView"

// Wave 197 SW4 — NewsCardView Storybook fixture (CONTEXT-tier, complex).
//
// Full presentation card: hero + content + spotlight overlay + quick-view popover
// + admin menu + edit/delete dialogs (lazy via Suspense). Pure presentation —
// every interaction is a prop callback. The `spotlight` prop is supplied by the
// real useSpotlight() hook in a harness (no MotionValue mock needed), wrapped in
// <LazyMotion features={domAnimation}> for the m.* tree.
//
// Variants: Default / Liked / AdminBookmarked / DarkMode.

type HarnessProps = Omit<NewsCardViewProps, "spotlight">

function NewsCardHarness(props: HarnessProps) {
  const spotlight = useSpotlight()
  return <NewsCardView {...props} spotlight={spotlight} />
}

const BASE: HarnessProps = {
  id: "n1",
  title: "University Launches New Interdisciplinary Research Lab",
  created_at: "2026-05-20T09:00:00Z",
  image_url: "https://picsum.photos/seed/newscardview/800/400",
  previewText:
    "The new facility hosts teams working across data science, robotics, and computational biology.",
  isLiked: false,
  likesCount: 128,
  commentsCount: 23,
  isBookmarked: false,
  isAdmin: false,
  loading: false,
  error: "",
  hoveringDisabled: false,
  readingTime: 5,
  category: "science",
  editOpen: false,
  confirmDeleteOpen: false,
  editData: { title: "", content: "", title_en: "", content_en: "", image_url: "" },
  onToggleLike: () => {},
  onToggleBookmark: () => {},
  onEditOpen: () => {},
  onEditClose: () => {},
  onDeleteOpen: () => {},
  onDeleteClose: () => {},
  onDeleteConfirm: () => {},
  onEditSuccess: () => {},
  onErrorClose: () => {},
  t: {
    deleteTitle: "Delete article?",
    deleteDesc: "This action cannot be undone.",
    confirm: "Delete",
    cancel: "Cancel",
  },
}

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <LazyMotion features={domAnimation}>
      <div className={dark ? "dark" : undefined}>
        <div className="news-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
          <div style={{ width: 380 }}>
            <Story />
          </div>
        </div>
      </div>
    </LazyMotion>
  )
}

const meta: Meta<typeof NewsCardView> = {
  title: "News/NewsCardView",
  component: NewsCardView,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof NewsCardView>

export const Default: Story = {
  render: () => <NewsCardHarness {...BASE} />,
  decorators: [themed(false)],
}

export const Liked: Story = {
  render: () => <NewsCardHarness {...BASE} isLiked likesCount={129} />,
  decorators: [themed(false)],
}

export const AdminBookmarked: Story = {
  render: () => <NewsCardHarness {...BASE} isAdmin isBookmarked />,
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  render: () => <NewsCardHarness {...BASE} isLiked likesCount={129} isBookmarked />,
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
