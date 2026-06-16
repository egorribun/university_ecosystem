import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, it, expect, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))
vi.mock("@/api/news", () => ({
  updateNews: vi.fn(() => Promise.resolve({ data: {} })),
  uploadNewsImage: vi.fn(() => Promise.resolve("")),
}))

import { NewsDetailEditDialog } from "@/components/news/NewsDetailEditDialog"

const initialData = {
  title: "Запуск новой кампусной экосистемы",
  content: "Единая платформа: расписание, новости, события и мессенджер.",
  title_en: "Launching the new campus ecosystem",
  content_en: "A unified platform for schedule, news, events, and messenger.",
  image_url: "https://picsum.photos/seed/news-detail-edit/800/400",
}

const baseProps = {
  open: true,
  onClose: vi.fn(),
  newsId: "news-1",
  language: "ru",
  initialData,
  onSuccess: vi.fn(),
  onError: vi.fn(),
}

function renderDialog(props = baseProps) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <NewsDetailEditDialog {...props} />
    </QueryClientProvider>
  )
}

describe("NewsDetailEditDialog", () => {
  it("renders the form prefilled from initialData when open", () => {
    renderDialog()
    expect(screen.getByText("news:dialogs.edit.title")).toBeInTheDocument()
    expect(screen.getByDisplayValue(initialData.title)).toBeInTheDocument()
    expect(screen.getByDisplayValue(initialData.title_en)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "common:buttons.save" })).toBeEnabled()
  })

  it("does not render the dialog body when closed", () => {
    renderDialog({ ...baseProps, open: false })
    expect(screen.queryByText("news:dialogs.edit.title")).not.toBeInTheDocument()
  })

  it("fires onClose when cancel is clicked", async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    renderDialog({ ...baseProps, onClose })
    await user.click(screen.getByRole("button", { name: "common:buttons.cancel" }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it("disables save when the title is cleared", async () => {
    const user = userEvent.setup()
    renderDialog()
    await user.clear(screen.getByDisplayValue(initialData.title))
    expect(screen.getByRole("button", { name: "common:buttons.save" })).toBeDisabled()
  })
})
