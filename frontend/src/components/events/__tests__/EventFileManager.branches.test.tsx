import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach } from "vitest"

const mocks = vi.hoisted(() => ({
  post: vi.fn(() => Promise.resolve({ data: {} })),
  del: vi.fn(() => Promise.resolve({ data: {} })),
}))

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return {
    ...actual,
    default: { post: mocks.post, delete: mocks.del },
  }
})
vi.mock("@/app/logger", () => ({ logError: vi.fn() }))
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

import { EventFileManager } from "@/components/events/EventFileManager"
import type { Event, EventFile } from "@/types/Event"

const baseEvent: Event = {
  id: "evt-1",
  title: "React 19 Patterns Workshop",
  title_en: "React 19 Patterns Workshop",
  starts_at: "2026-06-15T14:00:00Z",
  ends_at: "2026-06-15T16:00:00Z",
  created_by: "admin-1",
  created_at: "2026-05-01T10:00:00Z",
  is_active: true,
  image_url_optimized: null,
  files: [
    {
      id: "f1",
      event_id: "evt-1",
      file_url: "/media/lecture-slides.pdf",
      description: "Lecture slides.pdf",
    },
    {
      id: "f2",
      event_id: "evt-1",
      file_url: "/media/reading-list.pdf",
      description: "Reading list.pdf",
    },
  ],
}

type Props = React.ComponentProps<typeof EventFileManager>

const makeProps = (overrides: Partial<Props> = {}): Props => ({
  event: baseEvent,
  canEdit: true,
  onUpdate: vi.fn(() => Promise.resolve()),
  onError: vi.fn(),
  onSuccess: vi.fn(),
  ...overrides,
})

const getFileInput = (): HTMLInputElement => {
  const inputs = document.querySelectorAll<HTMLInputElement>("input[type='file']")
  expect(inputs.length).toBeGreaterThan(0)
  return inputs[0]!
}

const makeFile = (name = "notes.pdf"): File =>
  new File(["binary-content"], name, { type: "application/pdf" })

// jsdom's file input is read-only and fireEvent.change cannot attach a real
// File for FormData to pick up on submit. Define a FileList-shaped value on the
// input so React's form action constructs FormData with the real File.
const selectFileViaInput = (file: File): void => {
  const input = getFileInput()
  const fileList = {
    0: file,
    length: 1,
    item: (i: number) => (i === 0 ? file : null),
    [Symbol.iterator]: function* () {
      yield file
    },
  }
  Object.defineProperty(input, "files", { value: fileList, configurable: true })
  fireEvent.change(input)
}

// React 19 form actions intercept the native submit event; jsdom does not run
// requestSubmit() on fireEvent.click, so submit the <form> directly.
const submitForm = (): void => {
  const form = document.querySelector("form")
  expect(form).not.toBeNull()
  fireEvent.submit(form!)
}

describe("EventFileManager branches", () => {
  beforeEach(() => {
    mocks.post.mockReset()
    mocks.post.mockResolvedValue({ data: {} })
    mocks.del.mockReset()
    mocks.del.mockResolvedValue({ data: {} })
  })

  it("disables the submit button until a file is selected", () => {
    render(<EventFileManager {...makeProps()} />)
    const submit = screen.getByRole("button", { name: "events:detail.upload.submit.label" })
    expect(submit).toBeDisabled()
  })

  it("selecting a file enables submit and shows the file name", () => {
    render(<EventFileManager {...makeProps()} />)
    selectFileViaInput(makeFile("syllabus.pdf"))
    expect(screen.getByText("syllabus.pdf")).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "events:detail.upload.submit.label" })
    ).not.toBeDisabled()
  })

  // NOTE: the api.post success/error paths require a non-empty File to survive
  // React 19's form-action FormData reconstruction. jsdom rebuilds FormData from
  // the DOM and serializes <input type=file> to a 0-byte File (verified via a
  // userEvent.upload + requestSubmit probe), so the upload happy/error network
  // paths are not exercisable in jsdom. We instead drive the empty-file error
  // branch (uploadState.status === "error") and the __upload_reset__ branch.
  it("submitting with no usable file shows the inline noFile error branch", async () => {
    const props = makeProps()
    render(<EventFileManager {...props} />)

    submitForm()

    await waitFor(() =>
      expect(screen.getByText("events:detail.upload.errors.noFile")).toBeInTheDocument()
    )
    expect(mocks.post).not.toHaveBeenCalled()
    expect(props.onUpdate).not.toHaveBeenCalled()
  })

  it("re-selecting a file after an error resets the inline error message", async () => {
    render(<EventFileManager {...makeProps()} />)
    submitForm()

    await waitFor(() =>
      expect(screen.getByText("events:detail.upload.errors.noFile")).toBeInTheDocument()
    )

    // Re-select triggers the __upload_reset__ branch in handleFileChange,
    // dispatching the reset action that returns { status: "idle" }.
    selectFileViaInput(makeFile("second.pdf"))
    await waitFor(() =>
      expect(screen.queryByText("events:detail.upload.errors.noFile")).not.toBeInTheDocument()
    )
  })

  it("deletes a file: calls api.delete, onSuccess and onUpdate", async () => {
    const props = makeProps()
    render(<EventFileManager {...props} />)
    const deleteButtons = screen.getAllByRole("button", {
      name: "events:detail.sections.files.deleteAria",
    })
    fireEvent.click(deleteButtons[0]!)

    await waitFor(() => expect(mocks.del).toHaveBeenCalledTimes(1))
    expect(mocks.del).toHaveBeenCalledWith("/events/file/f1")
    await waitFor(() =>
      expect(props.onSuccess).toHaveBeenCalledWith("events:detail.messages.fileDeleted")
    )
    await waitFor(() => expect(props.onUpdate).toHaveBeenCalled())
  })

  it("delete failure: calls onError and still calls onUpdate in finally", async () => {
    mocks.del.mockRejectedValueOnce(new Error("delete failed"))
    const props = makeProps()
    render(<EventFileManager {...props} />)
    const deleteButtons = screen.getAllByRole("button", {
      name: "events:detail.sections.files.deleteAria",
    })
    fireEvent.click(deleteButtons[0]!)

    await waitFor(() =>
      expect(props.onError).toHaveBeenCalledWith("events:detail.messages.fileDeleteFailed")
    )
    await waitFor(() => expect(props.onUpdate).toHaveBeenCalled())
  })

  it("renders a pending file as plain text with a disabled delete button", () => {
    const pendingEvent: Event = {
      ...baseEvent,
      files: [
        {
          id: "pending-123",
          event_id: "evt-1",
          file_url: "",
          description: "uploading.pdf",
        },
      ],
    }
    render(<EventFileManager {...makeProps({ event: pendingEvent })} />)
    // pending file renders as a <span>, not a download <a>
    expect(screen.getByText("uploading.pdf")).toBeInTheDocument()
    expect(screen.queryByRole("link")).not.toBeInTheDocument()
    const deleteButton = screen.getByRole("button", {
      name: "events:detail.sections.files.deleteAria",
    })
    expect(deleteButton).toBeDisabled()
  })

  it("renders the explicit pending label when a pending file has no description", () => {
    const pendingFile: EventFile & { pending?: boolean } = {
      id: "f9",
      event_id: "evt-1",
      file_url: "",
      description: null,
      pending: true,
    }
    const pendingEvent: Event = { ...baseEvent, files: [pendingFile] }
    render(<EventFileManager {...makeProps({ event: pendingEvent })} />)
    expect(screen.getByText("events:detail.sections.files.pending")).toBeInTheDocument()
  })

  it("clicking a disabled pending delete does not call api.delete", () => {
    const pendingEvent: Event = {
      ...baseEvent,
      files: [
        {
          id: "pending-xyz",
          event_id: "evt-1",
          file_url: "",
          description: "still-uploading.pdf",
        },
      ],
    }
    render(<EventFileManager {...makeProps({ event: pendingEvent })} />)
    const deleteButton = screen.getByRole("button", {
      name: "events:detail.sections.files.deleteAria",
    })
    fireEvent.click(deleteButton)
    expect(mocks.del).not.toHaveBeenCalled()
  })
})
