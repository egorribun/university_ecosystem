import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { LazyMotion, domAnimation } from "framer-motion"
import { NewsDetailEditDialog } from "./NewsDetailEditDialog"

// Wave 199 SW1 — NewsDetailEditDialog Storybook fixture (CONTEXT-tier, no infra).
//
// Detail-page edit dialog using the @/components/settings Dialog, which renders
// via createPortal to document.body and animates with framer-motion `m.div` →
// **default-theme only** (portal escapes `.dark`), layout "fullscreen",
// LazyMotion required. useQueryClient is ambient (preview QueryClientProvider);
// updateNews / uploadNewsImage are submit-path only (try/catch), so a static
// `open` story never hits the network on mount.
//
// Variants: Default.

const initialData = {
  title: "Запуск новой кампусной экосистемы",
  content:
    "Сегодня мы открываем единую платформу: расписание, новости, события и мессенджер в одном месте.",
  title_en: "Launching the new campus ecosystem",
  content_en:
    "Today we open a unified platform: schedule, news, events, and messenger in one place.",
  image_url: "https://picsum.photos/seed/news-detail-edit/800/400",
}

const withMotion: Decorator = (Story) => (
  <LazyMotion features={domAnimation}>
    <Story />
  </LazyMotion>
)

const meta: Meta<typeof NewsDetailEditDialog> = {
  title: "News/NewsDetailEditDialog",
  component: NewsDetailEditDialog,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
  decorators: [withMotion],
  args: {
    open: true,
    newsId: "news-1",
    language: "ru",
    initialData,
    onClose: () => {},
    onSuccess: () => {},
    onError: () => {},
  },
}

export default meta
type Story = StoryObj<typeof NewsDetailEditDialog>

export const Default: Story = {}
