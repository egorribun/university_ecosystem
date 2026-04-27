import type { Meta, StoryObj } from "@storybook/react-vite"
import { NewsFormDialog } from "./NewsFormDialog"
import { I18nextProvider } from "react-i18next"
import i18n from "@/i18n/config"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
    },
  },
})

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

export const Default: Story = {
  args: {
    open: true,
    onClose: () => {},
  },
}
