import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi, beforeEach } from "vitest"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { http, HttpResponse } from "msw"

import { server } from "@/tests/mocks/server"
import { NewsFormDialog } from "../NewsFormDialog"

// We must wrap the component in a QueryClientProvider because NewsFormDialog uses useQueryClient
const renderWithProviders = (ui: React.ReactElement) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })

  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

describe("NewsFormDialog", () => {
  const defaultProps = {
    open: true,
    onClose: vi.fn(),
    onSuccess: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
    server.resetHandlers()
  })

  it("renders correctly when open", () => {
    renderWithProviders(<NewsFormDialog {...defaultProps} />)
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(screen.getByLabelText(/^Title(?! \()/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/^News text(?! \()/i)).toBeInTheDocument()
  })

  it("submits the form successfully and calls onSuccess and onClose", async () => {
    const user = userEvent.setup()

    server.use(
      http.post("*/news", async ({ request }) => {
        const body = (await request.json()) as { title: string; content: string }
        return HttpResponse.json({
          id: "123e4567-e89b-12d3-a456-426614174000",
          title: body.title,
          content: body.content,
          created_at: new Date().toISOString(),
          image_url_optimized: null,
          likes_count: 0,
          comments_count: 0,
          is_liked: false,
        })
      })
    )

    renderWithProviders(<NewsFormDialog {...defaultProps} />)

    const titleInput = screen.getByLabelText(/^Title(?! \()/i)
    const contentInput = screen.getByLabelText(/^News text(?! \()/i)

    await user.type(titleInput, "My Breaking News")
    await user.type(contentInput, "This is the content of the news.")

    const submitBtn = screen.getByRole("button", { name: /Publish/i })
    await user.click(submitBtn)

    await waitFor(() => {
      expect(defaultProps.onSuccess).toHaveBeenCalledTimes(1)
    })
    expect(defaultProps.onClose).toHaveBeenCalledTimes(1)
  })

  it("displays server error upon submission failure", async () => {
    const user = userEvent.setup()

    server.use(
      http.post("*/news", () => {
        return HttpResponse.json({ detail: "Title must be unique" }, { status: 400 })
      })
    )

    renderWithProviders(<NewsFormDialog {...defaultProps} />)

    const titleInput = screen.getByLabelText(/^Title(?! \()/i)
    const contentInput = screen.getByLabelText(/^News text(?! \()/i)

    await user.type(titleInput, "Duplicate News")
    await user.type(contentInput, "This is the content of the duplicate news.")

    const submitBtn = screen.getByRole("button", { name: /Publish/i })
    await user.click(submitBtn)

    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent("Title must be unique")

    // Ensure dialog remains open
    expect(defaultProps.onClose).not.toHaveBeenCalled()
    expect(defaultProps.onSuccess).not.toHaveBeenCalled()
  })
})
