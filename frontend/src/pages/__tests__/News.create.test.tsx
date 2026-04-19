import type { ReactNode } from "react"
import userEvent from "@testing-library/user-event"
import { screen, within } from "@testing-library/react"
import { QueryClient } from "@tanstack/react-query"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

vi.mock("@/api/news", () => ({
  createNews: vi.fn(),
  uploadNewsImage: vi.fn(),
}))

vi.mock("@/components/ui/Dialog", () => {
  const MockDialog = ({
    open,
    children,
    footer,
    title,
  }: {
    open: boolean
    children: ReactNode
    footer?: ReactNode
    title?: ReactNode
  }) => {
    if (!open) return null
    return (
      <div role="dialog">
        {title ? <h2>{title}</h2> : null}
        <div>{children}</div>
        {footer}
      </div>
    )
  }

  MockDialog.displayName = "MockDialog"

  return {
    __esModule: true,
    default: MockDialog,
  }
})

vi.mock("@/api/hooks/news", () => ({
  useNewsListQuery: () => ({
    news: [],
    isLoading: false,
    isFetching: false,
    refetch: vi.fn(),
    hasNextPage: false,
    fetchNextPage: vi.fn(),
    isFetchingNextPage: false,
  }),
}))

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { id: 1, role: "admin" },
  }),
  AuthProvider: ({ children }: { children: ReactNode }) => children,
}))

vi.mock("../../contexts/LanguageContext", () => ({
  useLanguage: () => ({
    language: "en" as const,
    setLanguage: vi.fn(),
    available: ["en", "ru"] as const,
  }),
  LanguageProvider: ({ children }: { children: ReactNode }) => children,
}))

import News from "../News"
import { createNews } from "@/api/news"

const createNewsMock = vi.mocked(createNews)

const renderNews = async () => {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })

  return renderWithRouter({
    ui: News,
    queryClient: client,
  })
}

describe("News creation dialog", () => {
  beforeEach(() => {
    createNewsMock.mockReset()
  })

  it("keeps the dialog open and surfaces errors when creation fails", async () => {
    const user = userEvent.setup()
    const errorMessage = "Title already exists"

    createNewsMock.mockRejectedValueOnce({
      isAxiosError: true,
      response: { data: { detail: errorMessage } },
    })

    await renderNews()

    const addButtons = screen.getAllByRole("button", { name: /\+ add news/i })
    await user.click(addButtons[0]!)

    const dialog = await screen.findByRole("dialog")

    const titleInput = await within(dialog).findByLabelText(/^Title(?! \()/)
    const contentInput = await within(dialog).findByLabelText(/^News text(?! \()/)

    await user.type(titleInput, "Test headline")
    await user.type(contentInput, "Test content body")

    await user.click(screen.getByRole("button", { name: /publish/i }))

    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent(errorMessage)
    expect(titleInput).toHaveValue("Test headline")
    expect(contentInput).toHaveValue("Test content body")
    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })
})
