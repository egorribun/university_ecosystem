import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { http, HttpResponse } from "msw"

const apiMocks = vi.hoisted(() => ({
  uploadNewsImage: vi.fn(),
}))

const telemetryMocks = vi.hoisted(() => ({
  run: vi.fn(<T,>(operation: () => T): T => operation()),
  capture: vi.fn(),
}))

telemetryMocks.capture.mockImplementation(() => ({ run: telemetryMocks.run }))

vi.mock("@/api/news", async () => {
  const actual = await vi.importActual<typeof import("@/api/news")>("@/api/news")
  return {
    ...actual,
    uploadNewsImage: apiMocks.uploadNewsImage,
  }
})

vi.mock("@/utils/telemetryContext", () => ({
  captureActiveTelemetryContext: telemetryMocks.capture,
}))

import { server } from "@/tests/mocks/server"
import { NewsFormDialog } from "../NewsFormDialog"

// We must wrap the component in a QueryClientProvider because NewsFormDialog uses useQueryClient
const renderWithProviders = (ui: React.ReactElement) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })

  return {
    ...render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>),
    queryClient,
  }
}

describe("NewsFormDialog", () => {
  const defaultProps = {
    open: true,
    onClose: vi.fn(),
    onSuccess: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
    telemetryMocks.capture.mockImplementation(() => ({ run: telemetryMocks.run }))
    server.resetHandlers()
  })

  afterEach(() => {
    vi.restoreAllMocks()
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

    const { queryClient } = renderWithProviders(<NewsFormDialog {...defaultProps} />)
    const invalidateQueries = vi.spyOn(queryClient, "invalidateQueries")

    const titleInput = screen.getByLabelText(/^Title(?! \()/i)
    const contentInput = screen.getByLabelText(/^News text(?! \()/i)

    await user.type(titleInput, "My Breaking News")
    await user.type(contentInput, "This is the content of the news.")

    const submitBtn = screen.getByRole("button", { name: /Publish/i })
    await user.click(submitBtn)

    await waitFor(() => {
      expect(defaultProps.onSuccess).toHaveBeenCalledTimes(1)
    })
    expect(invalidateQueries).toHaveBeenCalledTimes(1)
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["news", "list"] })
    expect(telemetryMocks.run).toHaveBeenCalledTimes(3)
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

  it("previews an image and submits optional English fields with the uploaded URL", async () => {
    const user = userEvent.setup()
    const createPayloads: Array<Record<string, unknown>> = []
    const objectUrl = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:news-preview")

    server.use(
      http.post("*/news", async ({ request }) => {
        createPayloads.push((await request.json()) as Record<string, unknown>)
        return HttpResponse.json({
          id: "123e4567-e89b-12d3-a456-426614174000",
          title: "My Breaking News",
          content: "This is the content of the news.",
          title_en: "Breaking News",
          content_en: "English content",
          created_at: new Date().toISOString(),
          image_url_optimized: "https://cdn.example.com/news-cover.png",
          likes_count: 0,
          comments_count: 0,
          is_liked: false,
        })
      })
    )
    apiMocks.uploadNewsImage.mockResolvedValueOnce("https://cdn.example.com/news-cover.png")

    renderWithProviders(<NewsFormDialog {...defaultProps} />)
    const imageInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const image = new File(["png-bytes"], "cover.png", { type: "image/png" })
    await user.upload(imageInput, image)

    expect(objectUrl).toHaveBeenCalledWith(image)
    expect(screen.getByText(/Change photo/i)).toBeInTheDocument()
    expect(screen.getByRole("img", { name: /new cover/i })).toHaveAttribute(
      "src",
      "blob:news-preview"
    )

    await user.type(screen.getByLabelText(/^Title(?! \()/i), "My Breaking News")
    await user.type(screen.getByLabelText(/^News text(?! \()/i), "This is the content of the news.")
    await user.type(screen.getByLabelText(/Title \(English\)/i), "Breaking News")
    await user.type(screen.getByLabelText(/News text \(English\)/i), "English content")
    const submitBtn = screen.getByRole("button", { name: /Publish/i })
    await waitFor(() => expect(submitBtn).toBeEnabled())
    await user.click(submitBtn)

    await waitFor(() => expect(defaultProps.onSuccess).toHaveBeenCalledTimes(1))
    expect(apiMocks.uploadNewsImage).toHaveBeenCalledWith(image)
    expect(createPayloads).toHaveLength(1)
    expect(createPayloads[0]).toMatchObject({
      title: "My Breaking News",
      content: "This is the content of the news.",
      image_url: "https://cdn.example.com/news-cover.png",
      title_en: "Breaking News",
      content_en: "English content",
    })
  })

  it("shows image validation errors and resets fields after reopening", async () => {
    const user = userEvent.setup()
    const { rerender } = renderWithProviders(<NewsFormDialog {...defaultProps} />)
    const imageInput = document.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(imageInput, new File(["gif"], "cover.gif", { type: "image/gif" }))

    expect(
      await screen.findByText(/Only \.jpg, \.jpeg, \.png and \.webp formats are supported/i)
    ).toBeInTheDocument()

    await user.type(screen.getByLabelText(/^Title(?! \()/i), "Temporary title")
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <NewsFormDialog {...defaultProps} open={false} />
      </QueryClientProvider>
    )
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <NewsFormDialog {...defaultProps} open={true} />
      </QueryClientProvider>
    )
    expect(screen.getByLabelText(/^Title(?! \()/i)).toHaveValue("")
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("handles message-shaped and network submission errors without closing", async () => {
    const user = userEvent.setup()
    server.use(
      http.post("*/news", () =>
        HttpResponse.json({ message: "Publishing is temporarily disabled" }, { status: 503 })
      )
    )
    renderWithProviders(<NewsFormDialog {...defaultProps} />)
    await user.type(screen.getByLabelText(/^Title(?! \()/i), "Unavailable")
    await user.type(screen.getByLabelText(/^News text(?! \()/i), "Please retry later")
    await user.click(screen.getByRole("button", { name: /Publish/i }))
    expect(await screen.findByRole("alert")).toHaveTextContent("Publishing is temporarily disabled")
    expect(defaultProps.onClose).not.toHaveBeenCalled()

    server.use(http.post("*/news", () => HttpResponse.error()))
    await user.click(screen.getByRole("button", { name: /Publish/i }))
    expect(await screen.findByRole("alert")).toHaveTextContent(/network error|network error/i)
  })

  it("allows cancelling and supports a dialog without an onSuccess callback", async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    renderWithProviders(<NewsFormDialog open={true} onClose={onClose} />)
    await user.click(screen.getByRole("button", { name: /Cancel/i }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it("renders required and optional English validation messages", async () => {
    renderWithProviders(<NewsFormDialog {...defaultProps} />)
    fireEvent.submit(document.querySelector("form")!)

    expect(await screen.findByText("Title is required")).toBeInTheDocument()
    expect(screen.getByText("Content is required")).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/Title \(English\)/i), {
      target: { value: "x".repeat(101) },
    })
    fireEvent.change(screen.getByLabelText(/News text \(English\)/i), {
      target: { value: "x".repeat(3001) },
    })
    expect(
      await screen.findByText("Title (EN) must be less than 100 characters")
    ).toBeInTheDocument()
    expect(screen.getByText("Content (EN) must be less than 3000 characters")).toBeInTheDocument()
  })
})
