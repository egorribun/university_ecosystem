import type { Meta, StoryObj } from "@storybook/react-vite"
import { NewsFormDialog } from "./NewsFormDialog"
import { I18nextProvider } from "react-i18next"
import i18n from "@/i18n/config"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { NewsItem } from "@/api/news"

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
    },
  },
})

const sampleNews: NewsItem = {
  id: "1",
  title: "Existing News Article",
  title_en: "Existing News Article",
  content: "This is the content of an existing news article, being edited.",
  content_en: "This is the content of an existing news article, being edited.",
  summary: "Summary of existing article.",
  summary_en: "Summary of existing article.",
  tags: ["campus", "update"],
  is_published: true,
  published_at: new Date().toISOString(),
  author_id: "author-1",
  image_url_optimized: null,
  image_url_original: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
}

const meta = {
  title: "Features/News/NewsFormDialog",
  component: NewsFormDialog,
  parameters: {
    layout: "centered",
  },
  decorators: [
    (Story) => (
      <QueryClientProvider client={queryClient}>
        <I18nextProvider i18n={i18n}>
          <Story />
        </I18nextProvider>
      </QueryClientProvider>
    ),
  ],
  tags: ["autodocs"],
  argTypes: {
    onClose: { action: "onClose" },
  },
} satisfies Meta<typeof NewsFormDialog>

export default meta
type Story = StoryObj<typeof meta>

export const CreateMode: Story = {
  args: {
    isOpen: true,
    initialData: undefined,
  },
}

export const EditMode: Story = {
  args: {
    isOpen: true,
    initialData: sampleNews,
  },
}
