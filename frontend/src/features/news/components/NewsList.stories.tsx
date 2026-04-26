import type { Meta, StoryObj } from "@storybook/react-vite"
import { NewsList } from "./NewsList"
import { I18nextProvider } from "react-i18next"
import i18n from "@/i18n/config"
import { BrowserRouter } from "react-router-dom"
import type { NewsItem } from "@/api/news"

// Sample data for stories
const sampleNews: NewsItem[] = [
  {
    id: "1",
    title: "University Announces New AI Research Center",
    title_en: "University Announces New AI Research Center",
    content: "The university is thrilled to announce a state-of-the-art AI research center.",
    content_en: "The university is thrilled to announce a state-of-the-art AI research center.",
    summary: "New AI research center opening next fall.",
    summary_en: "New AI research center opening next fall.",
    tags: ["research", "ai", "campus"],
    is_published: true,
    published_at: new Date().toISOString(),
    author_id: "author-1",
    image_url_optimized:
      "https://images.unsplash.com/photo-1531482615713-2afd69097998?auto=format&fit=crop&q=80&w=1000",
    image_url_original: "https://images.unsplash.com/photo-1531482615713-2afd69097998",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "2",
    title: "Campus Library Extends Hours for Finals Week",
    title_en: "Campus Library Extends Hours for Finals Week",
    content: "To support students during finals week, the library will be open 24/7.",
    content_en: "To support students during finals week, the library will be open 24/7.",
    summary: "Library open 24/7 during finals.",
    summary_en: "Library open 24/7 during finals.",
    tags: ["library", "students"],
    is_published: true,
    published_at: new Date(Date.now() - 86400000).toISOString(),
    author_id: "author-1",
    image_url_optimized: null,
    image_url_original: null,
    created_at: new Date(Date.now() - 86400000).toISOString(),
    updated_at: new Date(Date.now() - 86400000).toISOString(),
  },
]

const meta = {
  title: "Features/News/NewsList",
  component: NewsList,
  parameters: {
    layout: "padded",
  },
  decorators: [
    (Story) => (
      <BrowserRouter>
        <I18nextProvider i18n={i18n}>
          <div className="max-w-4xl mx-auto mt-8">
            <Story />
          </div>
        </I18nextProvider>
      </BrowserRouter>
    ),
  ],
  tags: ["autodocs"],
  argTypes: {
    onEdit: { action: "onEdit" },
    onDelete: { action: "onDelete" },
  },
} satisfies Meta<typeof NewsList>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    items: sampleNews,
    isLoading: false,
    isAdmin: false,
  },
}

export const AdminView: Story = {
  args: {
    items: sampleNews,
    isLoading: false,
    isAdmin: true,
  },
}

export const Loading: Story = {
  args: {
    items: [],
    isLoading: true,
    isAdmin: false,
  },
}

export const Empty: Story = {
  args: {
    items: [],
    isLoading: false,
    isAdmin: false,
  },
}
