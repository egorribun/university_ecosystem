import type { Meta, StoryObj } from "@storybook/react-vite-vite"
import { NewsCard } from "./NewsCard"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { LanguageProvider } from "@/contexts/LanguageContext"
import { I18nextProvider } from "react-i18next"
import i18n from "@/i18n/config"

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
    },
  },
})

const meta: Meta<typeof NewsCard> = {
  title: "Dashboard/NewsCard",
  component: NewsCard,
  parameters: {
    layout: "centered",
  },
  decorators: [
    (Story) => (
      <QueryClientProvider client={queryClient}>
        <I18nextProvider i18n={i18n}>
          <LanguageProvider>
            <div style={{ width: "400px" }}>
              <Story />
            </div>
          </LanguageProvider>
        </I18nextProvider>
      </QueryClientProvider>
    ),
  ],
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof NewsCard>

export const Default: Story = {
  args: {
    locale: "ru-RU",
  },
  parameters: {
    msw: {
      handlers: [
        // Handlers would go here if using MSW addon
      ],
    },
  },
}

export const English: Story = {
  args: {
    locale: "en-US",
  },
}
