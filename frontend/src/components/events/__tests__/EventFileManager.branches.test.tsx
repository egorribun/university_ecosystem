import { render, screen, fireEvent, act } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach } from "vitest"

const mocks = vi.hoisted(() => {
  const telemetryState = { active: false }
  const run = vi.fn(<T,>(operation: () => T): T => {
    telemetryState.active = true
    try {
      return operation()
    } finally {
      telemetryState.active = false
    }
  })

  return {
    post: vi.fn(() => Promise.resolve({ data: {} })),
    del: vi.fn(() => Promise.resolve({ data: {} })),
    telemetryState,
    run,
    capture: vi.fn(() => ({ run })),
    logError: vi.fn(),
  }
})

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return {
    ...actual,
    default: { post: mocks.post, delete: mocks.del },
  }
})
vi.mock("@/app/logger", () => ({ logError: mocks.logError }))
vi.mock("@/utils/telemetryContext", () => ({
  captureActiveTelemetryContext: mocks.capture,
}))
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

import {
  createRemoveFileAction,
  createUploadErrorState,
  createUploadSuccessState,
  EventFileManager,
  getPendingFileAttribute,
  getSelectedFile,
  getUploadSubmitLabelKey,
  resetFileInputValue,
  shouldResetUploadError,
} from "@/components/events/EventFileManager"
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

describe("EventFileManager branches", () => {
  beforeEach(() => {
    mocks.post.mockReset()
    mocks.post.mockResolvedValue({ data: {} })
    mocks.del.mockReset()
    mocks.del.mockResolvedValue({ data: {} })
    mocks.capture.mockClear()
    mocks.run.mockClear()
    mocks.logError.mockClear()
    mocks.telemetryState.active = false
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

  it("clears the selected file when the browser reports an empty file list", () => {
    render(<EventFileManager {...makeProps()} />)
    const input = getFileInput()
    fireEvent.change(input, { target: { files: [] } })

    expect(screen.getByRole("button", { name: "events:detail.upload.submit.label" })).toBeDisabled()
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

    await flushAction()
    expect(screen.getByText("events:detail.upload.errors.noFile")).toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
    expect(props.onUpdate).not.toHaveBeenCalled()
  })

  it("starts in the explicit idle upload state", () => {
    render(<EventFileManager {...makeProps()} />)

    expect(document.querySelector("form")).toHaveAttribute("data-upload-state", "idle")
  })

  it("constructs explicit success and error upload states", () => {
    expect(createUploadSuccessState()).toEqual({ status: "success" })
    expect(createUploadErrorState("upload failed")).toEqual({
      status: "error",
      error: "upload failed",
    })
  })

  it("keeps file action and DOM serialization contracts pure", () => {
    expect(createRemoveFileAction("file-42")).toEqual({ type: "remove", id: "file-42" })
    expect(getUploadSubmitLabelKey(true)).toBe("events:detail.upload.submit.pending")
    expect(getUploadSubmitLabelKey(false)).toBe("events:detail.upload.submit.label")
    expect(getPendingFileAttribute(true)).toBe("true")
    expect(getPendingFileAttribute(false)).toBe("false")

    const file = makeFile("contract.pdf")
    const files = {
      0: file,
      length: 1,
      item: (index: number) => (index === 0 ? file : null),
    } as unknown as FileList
    expect(getSelectedFile(files)).toBe(file)
    expect(getSelectedFile(null)).toBeNull()
    expect(getSelectedFile(undefined)).toBeNull()
    expect(shouldResetUploadError({ status: "error", error: "failed" }, false)).toBe(true)
    expect(shouldResetUploadError({ status: "error", error: "failed" }, true)).toBe(false)
    expect(shouldResetUploadError({ status: "idle" }, false)).toBe(false)
    expect(shouldResetUploadError({ status: "success" }, false)).toBe(false)
  })

  it("resets only a mounted file input", () => {
    const input = document.createElement("input")
    input.type = "file"
    const valueSetter = vi.spyOn(HTMLInputElement.prototype, "value", "set")

    expect(() => resetFileInputValue(null)).not.toThrow()
    resetFileInputValue(input)

    expect(valueSetter).toHaveBeenCalledWith("")
    valueSetter.mockRestore()
  })

  it("captures telemetry synchronously at the DOM submit boundary", () => {
    render(<EventFileManager {...makeProps()} />)
    const form = document.querySelector("form")
    expect(form).not.toBeNull()
    form!.addEventListener("submit", (event) => event.preventDefault(), { once: true })

    fireEvent.submit(form!)

    expect(mocks.capture).toHaveBeenCalledTimes(1)
    expect(mocks.post).not.toHaveBeenCalled()
  })

  it("executes the upload request inside the captured telemetry context", async () => {
    const props = makeProps()
    const file = makeFile("telemetry.pdf")
    render(<EventFileManager {...props} />)

    await withFormFile(file, async () => {
      selectFileViaInput(file)
      const form = document.querySelector("form")
      expect(form).not.toBeNull()

      await act(async () => {
        fireEvent.submit(form!)
        await Promise.resolve()
        await Promise.resolve()
      })

      expect(mocks.post).toHaveBeenCalledWith("/events/evt-1/upload_file", expect.any(FormData))
      expect(mocks.run).toHaveBeenCalled()
    })
  })

  it("re-selecting a file after an error resets the inline error message", async () => {
    render(<EventFileManager {...makeProps()} />)
    submitForm()

    await flushAction()
    expect(screen.getByText("events:detail.upload.errors.noFile")).toBeInTheDocument()

    // Re-select triggers the __upload_reset__ branch in handleFileChange,
    // dispatching the reset action that returns { status: "idle" }.
    selectFileViaInput(makeFile("second.pdf"))
    await flushAction()
    expect(screen.queryByText("events:detail.upload.errors.noFile")).not.toBeInTheDocument()
    expect(document.querySelector("form")).toHaveAttribute("data-upload-state", "idle")
  })

  it("uploads a selected file, removes the optimistic row, and refreshes the event", async () => {
    mocks.post.mockImplementationOnce(() => {
      expect(mocks.telemetryState.active).toBe(true)
      return Promise.resolve({ data: {} })
    })
    const onUpdate = vi.fn(() => {
      expect(mocks.telemetryState.active).toBe(true)
      return Promise.resolve()
    })
    const props = makeProps({ onUpdate })
    const file = makeFile("slides.pdf")
    render(<EventFileManager {...props} />)

    await withFormFile(file, async () => {
      selectFileViaInput(file)
      submitForm()

      await flushAction()
      expect(mocks.post).toHaveBeenCalledWith("/events/evt-1/upload_file", expect.any(FormData))
      expect(props.onSuccess).toHaveBeenCalledWith("events:detail.messages.fileAdded")
      expect(props.onUpdate).toHaveBeenCalledTimes(1)
    })

    expect(mocks.capture).toHaveBeenCalledTimes(1)
    expect(mocks.run).toHaveBeenCalledTimes(2)
    expect(screen.queryByText("slides.pdf")).not.toBeInTheDocument()
    await flushAction()
    expect(document.querySelector("form")).toHaveAttribute("data-upload-state", "success")
    expect(document.querySelector("[data-file-id^='optimistic-']")).not.toBeInTheDocument()
  })

  it("completes an upload safely after the file input unmounts", async () => {
    let resolveUpload!: (value: { data: Record<string, never> }) => void
    mocks.post.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveUpload = resolve
      })
    )
    const props = makeProps()
    const file = makeFile("late.pdf")
    const view = render(<EventFileManager {...props} />)

    await withFormFile(file, async () => {
      selectFileViaInput(file)
      submitForm()
      await flushAction()
      expect(mocks.post).toHaveBeenCalledOnce()
      view.unmount()
      resolveUpload({ data: {} })
      await flushAction()
      expect(props.onSuccess).toHaveBeenCalled()
      expect(props.onUpdate).toHaveBeenCalledOnce()
    })

    expect(props.onError).not.toHaveBeenCalled()
    expect(screen.queryByText("late.pdf")).not.toBeInTheDocument()
  })

  it("removes the optimistic row before a slow refresh settles", async () => {
    let resolveUpdate!: () => void
    const onUpdate = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveUpdate = resolve
        })
    )
    const props = makeProps({ onUpdate })
    const file = makeFile("remove-before-refresh.pdf")
    render(<EventFileManager {...props} />)

    await withFormFile(file, async () => {
      try {
        selectFileViaInput(file)
        submitForm()

        await flushAction()
        expect(mocks.post).toHaveBeenCalledOnce()
        expect(onUpdate).toHaveBeenCalledOnce()
        expect(document.querySelector("[data-file-id^='optimistic-']")).not.toBeInTheDocument()
        resolveUpdate()
        await flushAction()
        expect(props.onSuccess).toHaveBeenCalledWith("events:detail.messages.fileAdded")
        expect(document.querySelector("form")).toHaveAttribute("data-upload-state", "success")
      } finally {
        // If an injected mutation fails before onUpdate is observed, settle the
        // deferred callback so the mutant test process cannot remain pending.
        resolveUpdate?.()
      }
    })
  })

  it("uses an Axios detail when upload fails", async () => {
    const props = makeProps()
    const file = makeFile("large.pdf")
    mocks.post.mockRejectedValueOnce(
      Object.assign(new Error("quota"), {
        isAxiosError: true,
        response: { data: { detail: "File quota exceeded" } },
      })
    )
    render(<EventFileManager {...props} />)

    await withFormFile(file, async () => {
      selectFileViaInput(file)
      submitForm()

      await flushAction()
      expect(props.onError).toHaveBeenCalledWith("File quota exceeded")
    })
    expect(props.onSuccess).not.toHaveBeenCalled()
    expect(document.querySelector("[data-file-id^='optimistic-']")).not.toBeInTheDocument()
    await flushAction()
    expect(document.querySelector("form")).toHaveAttribute("data-upload-state", "error")
    expect(mocks.logError).toHaveBeenCalledWith(
      "[EventFileManager] Upload failed:",
      expect.anything()
    )
  })

  it("uses the generic upload failure message for non-Axios errors", async () => {
    const props = makeProps()
    const file = makeFile("broken.pdf")
    mocks.post.mockRejectedValueOnce(new Error("network down"))
    render(<EventFileManager {...props} />)

    await withFormFile(file, async () => {
      selectFileViaInput(file)
      submitForm()

      await flushAction()
      expect(props.onError).toHaveBeenCalledWith("events:detail.messages.fileAddFailed")
      expect(screen.getByText("events:detail.upload.errors.failed")).toBeInTheDocument()
    })
    expect(document.querySelector("[data-file-id^='optimistic-']")).not.toBeInTheDocument()
    expect(mocks.logError).toHaveBeenCalledWith(
      "[EventFileManager] Upload failed:",
      expect.anything()
    )
  })

  it("deletes a file: calls api.delete, onSuccess and onUpdate", async () => {
    const props = makeProps()
    render(<EventFileManager {...props} />)
    const deleteButtons = screen.getAllByRole("button", {
      name: "events:detail.sections.files.deleteAria",
    })
    fireEvent.click(deleteButtons[0]!)

    await flushAction()
    expect(mocks.del).toHaveBeenCalledTimes(1)
    expect(mocks.del).toHaveBeenCalledWith("/events/file/f1")
    expect(props.onSuccess).toHaveBeenCalledWith("events:detail.messages.fileDeleted")
    expect(props.onUpdate).toHaveBeenCalled()
    expect(mocks.logError).not.toHaveBeenCalled()
  })

  it("delete failure: calls onError and still calls onUpdate in finally", async () => {
    mocks.del.mockRejectedValueOnce(new Error("delete failed"))
    const props = makeProps()
    render(<EventFileManager {...props} />)
    const deleteButtons = screen.getAllByRole("button", {
      name: "events:detail.sections.files.deleteAria",
    })
    fireEvent.click(deleteButtons[0]!)

    await flushAction()
    expect(props.onError).toHaveBeenCalledWith("events:detail.messages.fileDeleteFailed")
    expect(props.onUpdate).toHaveBeenCalled()
    expect(mocks.logError).toHaveBeenCalledWith(
      "[EventFileManager] Delete failed:",
      expect.anything()
    )
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

  it("uses an empty-file fallback when a persisted file has no media URL", () => {
    const eventWithoutUrl: Event = {
      ...baseEvent,
      files: [
        {
          id: "f-empty-url",
          event_id: "evt-1",
          file_url: "",
          description: "attachment without url",
        },
      ],
    }
    render(<EventFileManager {...makeProps({ event: eventWithoutUrl, canEdit: false })} />)

    expect(
      screen.getByRole("link", { name: "events:detail.sections.files.downloadAria" })
    ).toHaveAttribute("href", "#")
  })

  it("treats an omitted files collection as empty", () => {
    const eventWithoutFiles = { ...baseEvent, files: undefined }
    render(<EventFileManager {...makeProps({ event: eventWithoutFiles })} />)

    expect(screen.getByText("events:detail.sections.files.empty")).toBeInTheDocument()
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

  it("renders the optimistic row contract while an upload is pending", async () => {
    let resolveUpload!: (value: { data: Record<string, never> }) => void
    mocks.post.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveUpload = resolve
      })
    )
    const file = makeFile("optimistic.pdf")
    render(<EventFileManager {...makeProps()} />)

    await withFormFile(file, async () => {
      selectFileViaInput(file)
      submitForm()

      await flushAction()
      const row = document.querySelector("[data-file-id^='optimistic-']")
      expect(row).toHaveAttribute("data-file-url", "")
      expect(row).toHaveAttribute("data-file-pending", "true")
      resolveUpload({ data: {} })
    })
  })

  it("serializes persisted files as non-pending rows", () => {
    render(<EventFileManager {...makeProps()} />)
    const rows = Array.from(document.querySelectorAll("[data-file-id]"))
    expect(rows).toHaveLength(2)
    expect(rows.map((row) => row.getAttribute("data-file-pending"))).toEqual(["false", "false"])
  })

  it("resets the file input value after a successful upload", async () => {
    const valueSetter = vi.spyOn(HTMLInputElement.prototype, "value", "set")
    const file = makeFile("reset.pdf")
    render(<EventFileManager {...makeProps()} />)

    await withFormFile(file, async () => {
      selectFileViaInput(file)
      submitForm()
      await flushAction()
      expect(mocks.post).toHaveBeenCalledOnce()
      expect(mocks.post).toHaveBeenCalledWith("/events/evt-1/upload_file", expect.any(FormData))
    })

    expect(valueSetter).toHaveBeenCalledWith("")
    valueSetter.mockRestore()
  })

  it("ignores a change event without a FileList", () => {
    render(<EventFileManager {...makeProps()} />)
    const input = getFileInput()

    expect(() => fireEvent.change(input, { target: { files: undefined } })).not.toThrow()
    expect(screen.getByRole("button", { name: "events:detail.upload.submit.label" })).toBeDisabled()
  })

  it("does not trust a detail field on a non-Axios error", async () => {
    const props = makeProps()
    const file = makeFile("spoofed.pdf")
    mocks.post.mockRejectedValueOnce({ response: { data: { detail: "spoofed detail" } } })
    render(<EventFileManager {...props} />)

    await withFormFile(file, async () => {
      selectFileViaInput(file)
      submitForm()
      await flushAction()
      expect(props.onError).toHaveBeenCalled()
    })

    expect(props.onError).toHaveBeenCalledWith("events:detail.messages.fileAddFailed")
  })

  it("uses the generic message when an Axios error has no response data", async () => {
    const props = makeProps()
    const file = makeFile("missing-response.pdf")
    mocks.post.mockRejectedValueOnce(
      Object.assign(new Error("missing response"), { isAxiosError: true })
    )
    render(<EventFileManager {...props} />)

    await withFormFile(file, async () => {
      selectFileViaInput(file)
      submitForm()
      await flushAction()
      expect(props.onError).toHaveBeenCalled()
    })

    expect(props.onError).toHaveBeenCalledWith("events:detail.messages.fileAddFailed")
  })

  it("uses the generic message when Axios response data has no detail", async () => {
    const props = makeProps()
    const file = makeFile("missing-detail.pdf")
    mocks.post.mockRejectedValueOnce(
      Object.assign(new Error("missing detail"), {
        isAxiosError: true,
        response: { data: undefined },
      })
    )
    render(<EventFileManager {...props} />)

    await withFormFile(file, async () => {
      selectFileViaInput(file)
      submitForm()
      await flushAction()
      expect(props.onError).toHaveBeenCalled()
    })

    expect(props.onError).toHaveBeenCalledWith("events:detail.messages.fileAddFailed")
  })
})
