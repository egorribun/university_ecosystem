import type { Meta, StoryObj } from "@storybook/react-vite"
import { NewsList } from "./NewsList"
import { I18nextProvider } from "react-i18next"
import i18n from "@/i18n/config"
import type { NewsItem } from "@/api/news"

// Sample data for stories
const sampleNews: NewsItem[] = [
  {
    id: "1",
    title: "University Announces New AI Research Center",
    title_en: "University Announces New AI Research Center",
    content: "The university is thrilled to announce a state-of-the-art AI research center.",
    content_en: "The university is thrilled to announce a state-of-the-art AI research center.",
    image_url_optimized:
      "https://images.unsplash.com/photo-1531482615713-2afd69097998?auto=format&fit=crop&q=80&w=1000",
    created_at: new Date().toISOString(),
  },
  {
    id: "2",
    title: "Campus Library Extends Hours for Finals Week",
    title_en: "Campus Library Extends Hours for Finals Week",
    content: "To support students during finals week, the library will be open 24/7.",
    content_en: "To support students during finals week, the library will be open 24/7.",
    image_url_optimized: null,
    created_at: new Date(Date.now() - 86400000).toISOString(),
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
      <I18nextProvider i18n={i18n}>
        <div className="max-w-4xl mx-auto mt-8">
          <Story />
        </div>
      </I18nextProvider>
    ),
  ],
  tags: ["autodocs"],
  argTypes: {
    refreshNews: { action: "refreshNews" },
    fetchNextPage: { action: "fetchNextPage" },
    onAddClick: { action: "onAddClick" },
  },
} satisfies Meta<typeof NewsList>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    newsList: sampleNews,
    isInitialLoading: false,
    isFetching: false,
    isFetchingNextPage: false,
    hasNextPage: false,
    fetchNextPage: () => {},
    refreshNews: () => {},
    onAddClick: () => {},
    isAdmin: false,
    isOnline: true,
  },
}

export const AdminView: Story = {
  args: {
    ...Default.args,
    isAdmin: true,
  },
}

export const Loading: Story = {
  args: {
    ...Default.args,
    newsList: [],
    isInitialLoading: true,
  },
}

export const Empty: Story = {
  args: {
    ...Default.args,
    newsList: [],
  },
}
