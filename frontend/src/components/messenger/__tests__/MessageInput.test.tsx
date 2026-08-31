import { render, screen, fireEvent, act } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

/**
 * Wave 183 SW11 — MessageInput unit tests.
 *
 * Covers W183 SW7 Blob URL lifecycle (critical regression guard) +
 * W183 SW4 a11y batch + baseline send/file behaviour.
 *
 * W183 SW7 Blob URL pattern under test:
 *  - URL.createObjectURL fires ONCE per file at add time (not per render)
 *  - URL.revokeObjectURL fires on removeFile
 *  - URL.revokeObjectURL fires on handleSend (files handed off to parent)
 *  - URL.revokeObjectURL fires on component unmount
 *
 * Also covers:
 *  - W183 SW4 textarea aria-label + 44x44 send/attach/remove buttons.
 *  - SVG rejection (security: only ext-typed image/svg+xml + xml-content
 *    sniff).
 *  - Enter sends, Shift+Enter does not.
 *  - Send button disabled when no text + no files.
 */

const createObjectURLSpy = vi.fn<(obj: Blob | MediaSource) => string>()
const revokeObjectURLSpy = vi.fn<(url: string) => void>()

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

vi.mock("@/components/media/SmartImage", () => ({
  default: ({ alt, className }: { alt?: string; className?: string }) => (
    <img alt={alt} className={className} />
  ),
}))

import { MessageInput } from "@/components/messenger/MessageInput"

let urlCounter = 0

beforeEach(() => {
  urlCounter = 0
  createObjectURLSpy.mockClear().mockImplementation(() => `blob:mock-${++urlCounter}`)
  revokeObjectURLSpy.mockClear()
  Object.defineProperty(URL, "createObjectURL", { value: createObjectURLSpy, writable: true })
  Object.defineProperty(URL, "revokeObjectURL", { value: revokeObjectURLSpy, writable: true })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("MessageInput", () => {
  describe("a11y (W183 SW4)", () => {
    it("textarea has aria-label", () => {
      render(<MessageInput onSend={() => {}} />)
      const textarea = screen.getByRole("textbox", { name: "messenger:typeMessage" })
      expect(textarea).toBeTruthy()
    })

    it("send button has aria-label", () => {
      render(<MessageInput onSend={() => {}} />)
      expect(screen.getByRole("button", { name: "messenger:aria.sendMessage" })).toBeTruthy()
    })

    it("attach button has aria-label", () => {
      render(<MessageInput onSend={() => {}} />)
      expect(screen.getByRole("button", { name: "messenger:aria.attachments" })).toBeTruthy()
    })

    it("send button has 44x44 touch target", () => {
      render(<MessageInput onSend={() => {}} />)
      const sendButton = screen.getByRole("button", { name: "messenger:aria.sendMessage" })
      expect(sendButton.className).toContain("min-h-[44px]")
      expect(sendButton.className).toContain("min-w-[44px]")
    })

    it("textarea exposes a UTF-16 envelope for the code-point boundary", () => {
      render(<MessageInput onSend={() => {}} />)
      const textarea = screen.getByRole("textbox", {
        name: "messenger:typeMessage",
      })

      expect(textarea).toHaveAttribute("maxLength", "65536")
    })

    it("counts Unicode code points when guarding composer input", () => {
      render(<MessageInput onSend={() => {}} />)
      const textarea = screen.getByRole("textbox", {
        name: "messenger:typeMessage",
      }) as HTMLTextAreaElement
      const limit = "😀".repeat(32_768)

      fireEvent.change(textarea, { target: { value: limit } })
      expect(textarea.value).toBe(limit)

      fireEvent.change(textarea, { target: { value: `${limit}😀` } })
      expect(textarea.value).toBe(limit)
    })

    it("reply cancel control has a 44x44 hit area", () => {
      render(
        <MessageInput
          onSend={() => {}}
          replyingTo={{ senderName: "Alice", isMe: false, text: "quoted" }}
          onCancelReply={() => {}}
        />
      )

      const cancelButton = screen.getByRole("button", { name: "common:buttons.cancel" })
      expect(cancelButton.className).toContain("min-h-[44px]")
      expect(cancelButton.className).toContain("min-w-[44px]")
    })

    it("attachment menu actions have a 44x44 hit area", () => {
      render(<MessageInput onSend={() => {}} />)
      fireEvent.click(screen.getByRole("button", { name: "messenger:aria.attachments" }))

      for (const type of ["photo", "document", "file"]) {
        const action = document.querySelector(`#chat-attach-type-${type}`)
        expect(action).toBeTruthy()
        expect(action?.className).toContain("min-h-[44px]")
        expect(action?.className).toContain("min-w-[44px]")
      }
    })
  })

  describe("send behaviour", () => {
    it("send button is disabled when no text + no files", () => {
      render(<MessageInput onSend={() => {}} />)
      const sendButton = screen.getByRole("button", { name: "messenger:aria.sendMessage" })
      expect(sendButton).toHaveProperty("disabled", true)
    })

    it("Enter key without text does NOT call onSend", () => {
      const onSend = vi.fn()
      render(<MessageInput onSend={onSend} />)
      const textarea = screen.getByRole("textbox", { name: "messenger:typeMessage" })

      fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false })
      expect(onSend).not.toHaveBeenCalled()
    })

    it("Enter key with text calls onSend", () => {
      const onSend = vi.fn()
      render(<MessageInput onSend={onSend} />)
      const textarea = screen.getByRole("textbox", { name: "messenger:typeMessage" })

      fireEvent.change(textarea, { target: { value: "Hello" } })
      fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false })

      expect(onSend).toHaveBeenCalledWith("Hello", [])
    })

    it("Shift+Enter does NOT trigger onSend (newline behaviour)", () => {
      const onSend = vi.fn()
      render(<MessageInput onSend={onSend} />)
      const textarea = screen.getByRole("textbox", { name: "messenger:typeMessage" })

      fireEvent.change(textarea, { target: { value: "Line 1" } })
      fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true })

      expect(onSend).not.toHaveBeenCalled()
    })

    it("Click send button calls onSend with text", () => {
      const onSend = vi.fn()
      render(<MessageInput onSend={onSend} />)
      const textarea = screen.getByRole("textbox", { name: "messenger:typeMessage" })
      const sendButton = screen.getByRole("button", { name: "messenger:aria.sendMessage" })

      fireEvent.change(textarea, { target: { value: "Hello" } })
      fireEvent.click(sendButton)

      expect(onSend).toHaveBeenCalledWith("Hello", [])
    })

    it("clears text after send", () => {
      render(<MessageInput onSend={() => {}} />)
      const textarea = screen.getByRole("textbox", {
        name: "messenger:typeMessage",
      }) as HTMLTextAreaElement
      const sendButton = screen.getByRole("button", { name: "messenger:aria.sendMessage" })

      fireEvent.change(textarea, { target: { value: "Hello" } })
      fireEvent.click(sendButton)

      expect(textarea.value).toBe("")
    })
  })

  describe("Blob URL lifecycle (W183 SW7 regression)", () => {
    it("createObjectURL fires ONCE per file at handleFileSelect time", async () => {
      const { container } = render(<MessageInput onSend={() => {}} />)
      const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement

      const file1 = new File(["a"], "a.png", { type: "image/png" })
      const file2 = new File(["b"], "b.png", { type: "image/png" })

      // Use Object.defineProperty since HTMLInputElement.files is readonly
      Object.defineProperty(fileInput, "files", {
        value: [file1, file2],
        writable: false,
      })

      await act(async () => {
        fireEvent.change(fileInput)
      })

      expect(createObjectURLSpy).toHaveBeenCalledTimes(2)
      expect(createObjectURLSpy).toHaveBeenNthCalledWith(1, file1)
      expect(createObjectURLSpy).toHaveBeenNthCalledWith(2, file2)
    })

    it("createObjectURL does NOT fire again on subsequent re-renders", async () => {
      const { container, rerender } = render(<MessageInput onSend={() => {}} />)
      const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement

      const file = new File(["a"], "a.png", { type: "image/png" })
      Object.defineProperty(fileInput, "files", { value: [file], writable: false })

      await act(async () => {
        fireEvent.change(fileInput)
      })

      const callsAfterAdd = createObjectURLSpy.mock.calls.length

      // Force several re-renders
      rerender(<MessageInput onSend={() => {}} />)
      rerender(<MessageInput onSend={() => {}} />)
      rerender(<MessageInput onSend={() => {}} />)

      // Pre-W183 SW7 the inline URL.createObjectURL(file) in SmartImage
      // srcRaw would fire on EVERY re-render. W183 SW7 moved it to
      // handleFileSelect ONCE. Verify the count stays stable.
      expect(createObjectURLSpy.mock.calls.length).toBe(callsAfterAdd)
    })

    it("revokeObjectURL fires when file is removed via X button", async () => {
      const { container } = render(<MessageInput onSend={() => {}} />)
      const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement

      const file = new File(["a"], "a.png", { type: "image/png" })
      Object.defineProperty(fileInput, "files", { value: [file], writable: false })

      await act(async () => {
        fireEvent.change(fileInput)
      })

      const removeButton = screen.getByRole("button", {
        name: "messenger:aria.removeAttachment",
      })

      expect(removeButton.className).toContain("min-h-[44px]")
      expect(removeButton.className).toContain("min-w-[44px]")

      revokeObjectURLSpy.mockClear()

      await act(async () => {
        fireEvent.click(removeButton)
      })

      expect(revokeObjectURLSpy).toHaveBeenCalledWith("blob:mock-1")
    })

    it("revokeObjectURL fires on handleSend (files handed off to parent)", async () => {
      const { container } = render(<MessageInput onSend={() => {}} />)
      const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
      const textarea = screen.getByRole("textbox", { name: "messenger:typeMessage" })
      const sendButton = screen.getByRole("button", { name: "messenger:aria.sendMessage" })

      const file = new File(["a"], "a.png", { type: "image/png" })
      Object.defineProperty(fileInput, "files", { value: [file], writable: false })

      await act(async () => {
        fireEvent.change(fileInput)
        fireEvent.change(textarea, { target: { value: "Hi" } })
      })

      revokeObjectURLSpy.mockClear()

      await act(async () => {
        fireEvent.click(sendButton)
      })

      expect(revokeObjectURLSpy).toHaveBeenCalledWith("blob:mock-1")
    })

    it("revokeObjectURL fires on component unmount", async () => {
      const { container, unmount } = render(<MessageInput onSend={() => {}} />)
      const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement

      const file = new File(["a"], "a.png", { type: "image/png" })
      Object.defineProperty(fileInput, "files", { value: [file], writable: false })

      await act(async () => {
        fireEvent.change(fileInput)
      })

      revokeObjectURLSpy.mockClear()

      unmount()

      expect(revokeObjectURLSpy).toHaveBeenCalledWith("blob:mock-1")
    })
  })

  describe("SVG rejection (security)", () => {
    it("rejects image/svg+xml MIME type", async () => {
      const { container } = render(<MessageInput onSend={() => {}} />)
      const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement

      const svgFile = new File(["<svg/>"], "evil.svg", { type: "image/svg+xml" })
      Object.defineProperty(fileInput, "files", { value: [svgFile], writable: false })

      await act(async () => {
        fireEvent.change(fileInput)
      })

      // SVG should be filtered out — no createObjectURL call.
      expect(createObjectURLSpy).not.toHaveBeenCalled()

      // Alert should appear
      expect(screen.getByRole("alert").textContent).toBe("messenger:svgNotAllowed")
    })

    it("rejects .svg extension even without image/svg+xml MIME", async () => {
      const { container } = render(<MessageInput onSend={() => {}} />)
      const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement

      const svgFile = new File(["<svg/>"], "Bad.SVG", { type: "image/png" })
      Object.defineProperty(fileInput, "files", { value: [svgFile], writable: false })

      await act(async () => {
        fireEvent.change(fileInput)
      })

      expect(createObjectURLSpy).not.toHaveBeenCalled()
    })

    it("accepts valid non-SVG image", async () => {
      const { container } = render(<MessageInput onSend={() => {}} />)
      const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement

      const pngFile = new File(["png-bytes"], "image.png", { type: "image/png" })
      Object.defineProperty(fileInput, "files", { value: [pngFile], writable: false })

      await act(async () => {
        fireEvent.change(fileInput)
      })

      expect(createObjectURLSpy).toHaveBeenCalledWith(pngFile)
    })
  })
})
