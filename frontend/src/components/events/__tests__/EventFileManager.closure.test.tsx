import { render, screen, fireEvent, act } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach } from "vitest"

const mocks = vi.hoisted(() => {
  const translationMock = vi.fn((key: string, options?: { label?: string }) =>
    options?.label ? `${key} [${options.label}]` : key
  )
  const useTranslationMock = vi.fn(() => ({
    t: translationMock,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }))
  const post = vi.fn(() => Promise.resolve({ data: {} }))
  const del = vi.fn(() => Promise.resolve({ data: {} }))
  const run = vi.fn(<T,>(operation: () => T): T => operation())
  const capture = vi.fn(() => ({ run }))
  return { translationMock, useTranslationMock, post, del, run, capture }
})

vi.mock("react-i18next", () => ({ useTranslation: mocks.useTranslationMock }))
vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>()
  return { ...actual, default: { ...actual.default, post: mocks.post, delete: mocks.del } }
})
vi.mock("@/app/logger", () => ({ logError: vi.fn() }))
vi.mock("@/utils/telemetryContext", () => ({
  captureActiveTelemetryContext: mocks.capture,
}))

import { EventFileManager } from "@/components/events/EventFileManager"
import type { Event, EventFile } from "@/types/Event"

const baseEvent: Event = {
  id: "evt-closure",
  title: "Accessible file manager",
  title_en: "Accessible file manager",
  starts_at: "2026-06-15T14:00:00Z",
  ends_at: "2026-06-15T16:00:00Z",
  created_by: "admin-1",
  created_at: "2026-05-01T10:00:00Z",
  is_active: true,
  image_url_optimized: null,
  files: [
    {
      id: "persisted-1",
      event_id: "evt-closure",
      file_url: "/media/readme.pdf",
      description: null,
    },
  ],
}

const makeProps = (overrides: Partial<React.ComponentProps<typeof EventFileManager>> = {}) => ({
  event: baseEvent,
  canEdit: true,
  onUpdate: vi.fn(() => Promise.resolve()),
  onError: vi.fn(),
  onSuccess: vi.fn(),
  ...overrides,
})

const makeFile = (name = "slides.pdf"): File =>
  new File(["pdf-content"], name, { type: "application/pdf" })

const getFileInput = (): HTMLInputElement => {
  const input = document.querySelector<HTMLInputElement>("input[type='file']")
  expect(input).not.toBeNull()
  return input!
}

const selectFile = (file: File): void => {
  const input = getFileInput()
  const fileList = {
    0: file,
    length: 1,
    item: (index: number) => (index === 0 ? file : null),
    [Symbol.iterator]: function* () {
      yield file
    },
  }
  Object.defineProperty(input, "files", { value: fileList, configurable: true })
  fireEvent.change(input)
}

const submitForm = (): void => {
  const form = document.querySelector("form")
  expect(form).not.toBeNull()
  fireEvent.submit(form!)
}

/** Flush React 19 form-action transitions without polling an unbounded promise. */
const flushAction = async (): Promise<void> => {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()
  })
}

const withFormFile = async (file: File, run: () => Promise<void>): Promise<void> => {
  const NativeFormData = globalThis.FormData
  class FormDataWithFile extends NativeFormData {
    constructor(form?: HTMLFormElement, submitter?: HTMLElement) {
      super(form, submitter)
      if (form) this.set("file", file)
    }
  }
  vi.stubGlobal("FormData", FormDataWithFile)
  try {
    await run()
  } finally {
    vi.stubGlobal("FormData", NativeFormData)
  }
}

describe("EventFileManager quality contract", () => {
  beforeEach(() => {
    mocks.useTranslationMock.mockClear()
    mocks.translationMock.mockClear()
    mocks.post.mockReset()
    mocks.del.mockReset()
    mocks.run.mockClear()
    mocks.capture.mockClear()
    mocks.post.mockResolvedValue({ data: {} })
    mocks.del.mockResolvedValue({ data: {} })
  })

  it("loads both translation namespaces and derives an accessible fallback file label", () => {
    render(<EventFileManager {...makeProps({ canEdit: false })} />)

    expect(mocks.useTranslationMock).toHaveBeenCalledWith(["events", "common"])
    expect(mocks.translationMock).toHaveBeenCalledWith(
      "events:detail.sections.files.downloadAria",
      { label: "readme.pdf" }
    )
    const link = screen.getByRole("link", {
      name: "events:detail.sections.files.downloadAria [readme.pdf]",
    })
    expect(link).toHaveTextContent("readme.pdf")
    expect(link).toHaveAttribute("title", "readme.pdf")
  })

  it("uses the explicit description instead of the URL basename", () => {
    const describedFile: EventFile = {
      id: "described",
      event_id: baseEvent.id,
      file_url: "/media/generated-name.pdf",
      description: "Course handout",
    }
    render(
      <EventFileManager
        {...makeProps({ canEdit: false, event: { ...baseEvent, files: [describedFile] } })}
      />
    )

    const link = screen.getByRole("link", {
      name: "events:detail.sections.files.downloadAria [Course handout]",
    })
    expect(link).toHaveTextContent("Course handout")
    expect(link).not.toHaveTextContent("generated-name.pdf")
  })

  it("recognizes a pending identifier as non-downloadable and keeps deletion disabled", () => {
    const pendingFile: EventFile = {
      id: "pending-from-server",
      event_id: baseEvent.id,
      file_url: "/media/still-uploading.pdf",
      description: null,
    }
    render(<EventFileManager {...makeProps({ event: { ...baseEvent, files: [pendingFile] } })} />)

    expect(screen.queryByRole("link")).not.toBeInTheDocument()
    expect(screen.getByText("events:detail.sections.files.pending")).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "events:detail.sections.files.deleteAria" })
    ).toBeDisabled()
  })

  it("shows the optimistic row and pending submit state until upload resolves", async () => {
    let resolveUpload!: (value: { data: Record<string, never> }) => void
    mocks.post.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveUpload = resolve
      })
    )
    const props = makeProps()
    const file = makeFile()
    render(<EventFileManager {...props} />)

    await withFormFile(file, async () => {
      selectFile(file)
      submitForm()

      await flushAction()
      expect(screen.getAllByText(file.name)).toHaveLength(2)
      expect(
        screen.getByRole("button", { name: "events:detail.upload.submit.pending" })
      ).toBeDisabled()
      expect(getFileInput()).toBeDisabled()
      resolveUpload({ data: {} })
      await flushAction()
      expect(props.onSuccess).toHaveBeenCalledWith("events:detail.messages.fileAdded")
    })

    expect(mocks.post).toHaveBeenCalledWith("/events/evt-closure/upload_file", expect.any(FormData))
    const postCalls = mocks.post.mock.calls as unknown as Array<[string, FormData]>
    const request = postCalls[0]?.[1]
    expect(request).toBeDefined()
    expect(request!.get("file")).toBe(file)
    expect(props.onUpdate).toHaveBeenCalledOnce()
    expect(screen.queryByText(file.name)).not.toBeInTheDocument()
    expect(getFileInput()).not.toBeDisabled()
  })

  it("keeps file actions stable while a slow delete resolves", async () => {
    let resolveDelete!: (value: { data: Record<string, never> }) => void
    mocks.del.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveDelete = resolve
      })
    )
    const props = makeProps({ canEdit: false })
    render(<EventFileManager {...props} canEdit />)
    const deleteButton = screen.getByRole("button", {
      name: "events:detail.sections.files.deleteAria",
    })

    fireEvent.click(deleteButton)
    await flushAction()
    expect(mocks.del).toHaveBeenCalledWith("/events/file/persisted-1")
    // The optimistic row is removed while the request is in flight; a
    // successful completion is reflected through callbacks and refresh.
    expect(screen.queryByRole("link", { name: /readme\.pdf/ })).toBeNull()
    resolveDelete({ data: {} })
    await flushAction()
    expect(props.onSuccess).toHaveBeenCalledWith("events:detail.messages.fileDeleted")
    expect(props.onUpdate).toHaveBeenCalledOnce()
  })
})
