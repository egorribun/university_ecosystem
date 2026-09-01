import { render, screen, fireEvent, act } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

/**
 * Sibling branch-coverage test for MessageInput (do NOT touch
 * MessageInput.test.tsx). The existing test covers a11y labels, the
 * Enter/Shift+Enter/click send path, SVG rejection (mime + extension), and the
 * Blob URL lifecycle (create-once / revoke on remove / send / unmount). This
 * file fills the remaining uncovered statement / cold-branch lines:
 *  - the attach menu open + the 3 attach-type buttons + handleAttachmentClick
 *    accept-switch (photo / document / file) + the hidden input .click() (127-142,
 *    289, 296, 301-326)
 *  - the <svg content-sniff rejection on an image-typed file (156)
 *  - the non-image file FileText preview branch (227-229)
 *  - the reply/quote compose chip — "You" vs name vs unknown-sender + cancel
 *    (255-275)
 *  - the onTyping keystroke callback + its optional no-op (342)
 *  - the reduced-motion anim-prop branches (96-97)
 *
 * Mocks mirror MessageInput.test.tsx (i18n key passthrough w/ opts echo,
 * SmartImage → img, Blob URL spies). framer-motion is stubbed via the shared
 * helper so the AnimatePresence-gated attach menu + alert render synchronously.
 */

const createObjectURLSpy = vi.fn<(obj: Blob | MediaSource) => string>()
const revokeObjectURLSpy = vi.fn<(url: string) => void>()
const mediaQueryMatchMock = vi.fn<(..._a: unknown[]) => boolean>(() => false)

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts ? `${key}|${JSON.stringify(opts)}` : key,
  }),
}))

vi.mock("@/components/media/SmartImage", () => ({
  default: ({ alt, className, srcRaw }: { alt?: string; className?: string; srcRaw?: string }) => (
    <img alt={alt} className={className} src={srcRaw} />
  ),
}))

vi.mock("@/hooks/useMediaQuery", () => ({ default: () => mediaQueryMatchMock() }))

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)

import { MessageInput } from "@/components/messenger/MessageInput"

let urlCounter = 0

const setFiles = (input: HTMLInputElement, files: File[]) => {
  Object.defineProperty(input, "files", { value: files, writable: false, configurable: true })
}

beforeEach(() => {
  urlCounter = 0
  createObjectURLSpy.mockClear().mockImplementation(() => `blob:mock-${++urlCounter}`)
  revokeObjectURLSpy.mockClear()
  mediaQueryMatchMock.mockReset().mockReturnValue(false)
  Object.defineProperty(URL, "createObjectURL", { value: createObjectURLSpy, writable: true })
  Object.defineProperty(URL, "revokeObjectURL", { value: revokeObjectURLSpy, writable: true })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("MessageInput branch coverage", () => {
  describe("attach menu + handleAttachmentClick (127-142, 289-326)", () => {
    it("opens the attach menu and renders the 3 attach-type buttons", () => {
      render(<MessageInput onSend={() => {}} />)
      const attachBtn = screen.getByRole("button", { name: "messenger:aria.attachments" })
      fireEvent.click(attachBtn)
      // 289/296 — open styling applied (rotate-45 on the Paperclip icon).
      expect(document.querySelector(".rotate-45")).toBeTruthy()
      // 308-323 — the three menu items render with i18n labels.
      expect(screen.getByText("messenger:attachPhoto")).toBeTruthy()
      expect(screen.getByText("messenger:attachDocument")).toBeTruthy()
      expect(screen.getByText("messenger:attachFile")).toBeTruthy()
    })

    it("clicking 'photo' closes the menu, sets the image accept filter, and clicks the input (130-131, 140)", () => {
      const { container } = render(<MessageInput onSend={() => {}} />)
      const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
      const clickSpy = vi.spyOn(fileInput, "click").mockImplementation(() => {})

      fireEvent.click(screen.getByRole("button", { name: "messenger:aria.attachments" }))
      fireEvent.click(screen.getByText("messenger:attachPhoto"))

      expect(fileInput.accept).toBe("image/png,image/jpeg,image/gif,image/webp")
      expect(clickSpy).toHaveBeenCalledTimes(1)
      // Menu closed after selection.
      expect(screen.queryByText("messenger:attachPhoto")).toBeNull()
      clickSpy.mockRestore()
    })

    it("clicking 'document' sets the document accept filter (133-134)", () => {
      const { container } = render(<MessageInput onSend={() => {}} />)
      const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
      const clickSpy = vi.spyOn(fileInput, "click").mockImplementation(() => {})

      fireEvent.click(screen.getByRole("button", { name: "messenger:aria.attachments" }))
      fireEvent.click(screen.getByText("messenger:attachDocument"))

      expect(fileInput.accept).toBe(".pdf,.doc,.docx,.txt")
      expect(clickSpy).toHaveBeenCalledTimes(1)
      clickSpy.mockRestore()
    })

    it("clicking 'file' sets the wildcard accept filter (136-137)", () => {
      const { container } = render(<MessageInput onSend={() => {}} />)
      const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
      const clickSpy = vi.spyOn(fileInput, "click").mockImplementation(() => {})

      fireEvent.click(screen.getByRole("button", { name: "messenger:aria.attachments" }))
      fireEvent.click(screen.getByText("messenger:attachFile"))

      expect(fileInput.accept).toBe("*")
      expect(clickSpy).toHaveBeenCalledTimes(1)
      clickSpy.mockRestore()
    })

    it("toggles the menu closed when the attach button is clicked again (showAttachMenu false branch)", () => {
      render(<MessageInput onSend={() => {}} />)
      const attachBtn = screen.getByRole("button", { name: "messenger:aria.attachments" })
      fireEvent.click(attachBtn)
      expect(screen.getByText("messenger:attachPhoto")).toBeTruthy()
      fireEvent.click(attachBtn)
      expect(screen.queryByText("messenger:attachPhoto")).toBeNull()
    })
  })

  describe("file preview + content-sniff (156, 227-229)", () => {
    it("ignores a change event whose file list is empty", async () => {
      const { container } = render(<MessageInput onSend={() => {}} />)
      const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
      setFiles(fileInput, [])

      await act(async () => {
        fireEvent.change(fileInput)
      })

      expect(createObjectURLSpy).not.toHaveBeenCalled()
    })

    it("renders a FileText preview (not an image) for a non-image attachment (227-229)", async () => {
      const { container } = render(<MessageInput onSend={() => {}} />)
      const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
      const pdf = new File(["%PDF-1.4"], "doc.pdf", { type: "application/pdf" })
      setFiles(fileInput, [pdf])

      await act(async () => {
        fireEvent.change(fileInput)
      })

      // handleFileSelect creates a previewUrl for EVERY accepted file (178), but
      // the chip render branches on file.type.startsWith("image/") (215): a PDF
      // takes the else branch → FileText icon preview (227-229), NOT a SmartImage.
      expect(createObjectURLSpy).toHaveBeenCalledWith(pdf)
      // The remove (X) button proves the attachment chip rendered.
      expect(screen.getByRole("button", { name: "messenger:aria.removeAttachment" })).toBeTruthy()
      // The non-image branch shows the FileText icon, not the preview <img>.
      expect(container.querySelector(".lucide-file-text")).toBeTruthy()
      expect(container.querySelector('img[alt="doc.pdf"]')).toBeNull()
    })

    it("takes the image content-sniff path + catch branch for an image file (152-161, catch 154/157)", async () => {
      // image/png MIME + .png extension passes the ext/mime guard at 149, so
      // execution reaches the `file.type.startsWith("image/")` sniff branch
      // (152) and the `file.slice(0, 512).text()` call. In jsdom Blob.text is
      // not implemented → it throws → the catch at 157 swallows it → the file
      // is accepted (161) → a preview Blob URL is created. This exercises the
      // image-sniff try/catch path. (Line 156's regex itself is unreachable in
      // jsdom because .text() throws before it — see returned notes.)
      const { container } = render(<MessageInput onSend={() => {}} />)
      const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
      const img = new File(["<svg xmlns='http://www.w3.org/2000/svg'></svg>"], "tricky.png", {
        type: "image/png",
      })
      const unreadablePrefix = new Blob([])
      Object.defineProperty(unreadablePrefix, "text", {
        configurable: true,
        value: vi.fn().mockRejectedValue(new Error("unreadable image prefix")),
      })
      vi.spyOn(img, "slice").mockReturnValue(unreadablePrefix)
      setFiles(fileInput, [img])

      await act(async () => {
        fireEvent.change(fileInput)
      })

      // Accepted via the catch path → a preview URL is created, no rejection.
      expect(createObjectURLSpy).toHaveBeenCalledWith(img)
      expect(screen.queryByRole("alert")).toBeNull()
    })

    it("rejects SVG markup found by the image content-sniff regex (156)", async () => {
      const { container } = render(<MessageInput onSend={() => {}} />)
      const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
      const img = new File(["not-used"], " disguised.png", { type: "image/png" })
      const sniffBlob = new Blob([])
      Object.defineProperty(sniffBlob, "text", {
        configurable: true,
        value: vi.fn().mockResolvedValue('  <?xml version="1.0"?>\n<svg viewBox="0 0 1 1">'),
      })
      vi.spyOn(img, "slice").mockReturnValue(sniffBlob)
      setFiles(fileInput, [img])

      await act(async () => {
        fireEvent.change(fileInput)
      })

      expect(screen.getByRole("alert").textContent).toBe("messenger:svgNotAllowed")
      expect(createObjectURLSpy).not.toHaveBeenCalled()
    })

    it("accepts image bytes when content sniffing proves they are not SVG", async () => {
      const { container } = render(<MessageInput onSend={() => {}} />)
      const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
      const image = new File(["png-bytes"], "safe.png", { type: "image/png" })
      const sniffBlob = new Blob([])
      Object.defineProperty(sniffBlob, "text", {
        configurable: true,
        value: vi.fn().mockResolvedValue("not svg content"),
      })
      vi.spyOn(image, "slice").mockReturnValue(sniffBlob)
      setFiles(fileInput, [image])

      await act(async () => {
        fireEvent.change(fileInput)
      })

      expect(createObjectURLSpy).toHaveBeenCalledWith(image)
      expect(screen.queryByRole("alert")).toBeNull()
    })
  })

  describe("reply/quote compose chip (255-275)", () => {
    it("renders the 'You' author label when replyingTo.isMe is true", () => {
      render(
        <MessageInput
          onSend={() => {}}
          replyingTo={{ senderName: "Anna", isMe: true, text: "the quoted text" }}
        />
      )
      // t("messenger:replyingTo", { name: t("messenger:replyTo.you") }) →
      // key|{"name":"messenger:replyTo.you"} with the opts-echo mock.
      expect(screen.getByText('messenger:replyingTo|{"name":"messenger:replyTo.you"}')).toBeTruthy()
      expect(screen.getByText("the quoted text")).toBeTruthy()
    })

    it("renders the sender name when replyingTo.isMe is false", () => {
      render(
        <MessageInput
          onSend={() => {}}
          replyingTo={{ senderName: "Boris", isMe: false, text: "boris said" }}
        />
      )
      expect(screen.getByText('messenger:replyingTo|{"name":"Boris"}')).toBeTruthy()
    })

    it("falls back to the unknown-sender label when senderName is null + not me (?? branch)", () => {
      render(
        <MessageInput
          onSend={() => {}}
          replyingTo={{ senderName: null, isMe: false, text: "anon" }}
        />
      )
      expect(
        screen.getByText('messenger:replyingTo|{"name":"messenger:replyTo.unknownSender"}')
      ).toBeTruthy()
    })

    it("cancel-reply X invokes onCancelReply (267-273)", () => {
      const onCancelReply = vi.fn()
      render(
        <MessageInput
          onSend={() => {}}
          onCancelReply={onCancelReply}
          replyingTo={{ senderName: "Anna", isMe: false, text: "x" }}
        />
      )
      fireEvent.click(screen.getByRole("button", { name: "common:buttons.cancel" }))
      expect(onCancelReply).toHaveBeenCalledTimes(1)
    })

    it("does NOT render the reply chip when replyingTo is null (255 ternary else)", () => {
      render(<MessageInput onSend={() => {}} replyingTo={null} />)
      expect(screen.queryByText(/messenger:replyingTo/)).toBeNull()
      expect(screen.queryByRole("button", { name: "common:buttons.cancel" })).toBeNull()
    })
  })

  describe("typing callback (342)", () => {
    it("calls onTyping on each keystroke when provided", () => {
      const onTyping = vi.fn()
      render(<MessageInput onSend={() => {}} onTyping={onTyping} />)
      const textarea = screen.getByRole("textbox", { name: "messenger:typeMessage" })
      fireEvent.change(textarea, { target: { value: "h" } })
      fireEvent.change(textarea, { target: { value: "hi" } })
      expect(onTyping).toHaveBeenCalledTimes(2)
    })

    it("does not throw when onTyping is omitted (optional ?. no-op)", () => {
      render(<MessageInput onSend={() => {}} />)
      const textarea = screen.getByRole("textbox", { name: "messenger:typeMessage" })
      expect(() => fireEvent.change(textarea, { target: { value: "hi" } })).not.toThrow()
    })
  })

  describe("reduced-motion anim props (96-97)", () => {
    it("renders with reduced-motion enabled (anim props become undefined)", () => {
      mediaQueryMatchMock.mockReturnValue(true)
      render(
        <MessageInput onSend={() => {}} replyingTo={{ senderName: "A", isMe: true, text: "t" }} />
      )
      // Component still renders the full UI; the whileHover/whileTap props are
      // stripped (undefined branch) — assert the structure is intact.
      expect(screen.getByRole("textbox", { name: "messenger:typeMessage" })).toBeTruthy()
      expect(screen.getByRole("button", { name: "messenger:aria.sendMessage" })).toBeTruthy()
    })
  })

  describe("svgRejected alert (166-167)", () => {
    it("shows the svgNotAllowed alert when a rejected file schedules the reset timer", async () => {
      // Adding an svg-extension file rejects it (149) → rejectedCount > 0 → the
      // setSvgRejected(true) + setTimeout(...) branch (166-168) fires. We assert
      // the alert appears (the 3s reset timer is left to run under real timers;
      // combining fake timers with the async Promise.all chain hangs jsdom).
      let resetAlert: (() => void) | undefined
      vi.spyOn(globalThis, "setTimeout").mockImplementation(((callback: TimerHandler) => {
        resetAlert = callback as () => void
        return 1
      }) as typeof setTimeout)
      const { container } = render(<MessageInput onSend={() => {}} />)
      const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
      const svgFile = new File(["<svg/>"], "evil.svg", { type: "image/svg+xml" })
      setFiles(fileInput, [svgFile])

      await act(async () => {
        fireEvent.change(fileInput)
      })

      expect(screen.getByRole("alert").textContent).toBe("messenger:svgNotAllowed")
      // No preview was created for the rejected file.
      expect(createObjectURLSpy).not.toHaveBeenCalled()

      act(() => resetAlert?.())
      expect(screen.queryByRole("alert")).toBeNull()
    })
  })

  describe("composer contract boundaries", () => {
    it("keeps the send action disabled for whitespace-only text", () => {
      const onSend = vi.fn()
      render(<MessageInput onSend={onSend} />)
      const textarea = screen.getByRole("textbox", { name: "messenger:typeMessage" })
      const sendButton = screen.getByRole("button", { name: "messenger:aria.sendMessage" })

      fireEvent.change(textarea, { target: { value: "   \n  " } })
      expect(sendButton).toBeDisabled()
      fireEvent.click(sendButton)
      expect(onSend).not.toHaveBeenCalled()
    })

    it("sends an attachment without text and clears the attachment state", async () => {
      const onSend = vi.fn()
      const { container } = render(<MessageInput onSend={onSend} />)
      const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
      const pdf = new File(["%PDF-1.4"], "document.pdf", { type: "application/pdf" })
      setFiles(fileInput, [pdf])

      await act(async () => {
        fireEvent.change(fileInput)
      })

      const sendButton = screen.getByRole("button", { name: "messenger:aria.sendMessage" })
      expect(sendButton).not.toBeDisabled()
      fireEvent.click(sendButton)

      expect(onSend).toHaveBeenCalledWith("", [pdf])
      expect(screen.queryByRole("button", { name: "messenger:aria.removeAttachment" })).toBeNull()
      expect(sendButton).toBeDisabled()
      expect(revokeObjectURLSpy).toHaveBeenCalledWith("blob:mock-1")
    })

    it("assigns stable IDs to duplicate files so removing one keeps the other", async () => {
      const { container } = render(<MessageInput onSend={() => {}} />)
      const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
      const duplicateA = new File(["same"], "duplicate.png", { type: "image/png" })
      const duplicateB = new File(["same"], "duplicate.png", { type: "image/png" })
      setFiles(fileInput, [duplicateA, duplicateB])

      await act(async () => {
        fireEvent.change(fileInput)
      })
      const removeButtons = screen.getAllByRole("button", {
        name: "messenger:aria.removeAttachment",
      })
      expect(removeButtons).toHaveLength(2)

      fireEvent.click(removeButtons[0]!)
      expect(
        screen.getAllByRole("button", { name: "messenger:aria.removeAttachment" })
      ).toHaveLength(1)
      expect(revokeObjectURLSpy).toHaveBeenCalledTimes(1)
    })

    it("rejects SVG markup without an XML declaration during image content sniffing", async () => {
      const { container } = render(<MessageInput onSend={() => {}} />)
      const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
      const image = new File(["not-used"], "vector.png", { type: "image/png" })
      const sniffBlob = new Blob([])
      Object.defineProperty(sniffBlob, "text", {
        configurable: true,
        value: vi.fn().mockResolvedValue('\n <svg viewBox="0 0 1 1">'),
      })
      vi.spyOn(image, "slice").mockReturnValue(sniffBlob)
      setFiles(fileInput, [image])

      await act(async () => {
        fireEvent.change(fileInput)
      })

      expect(screen.getByRole("alert")).toHaveTextContent("messenger:svgNotAllowed")
      expect(createObjectURLSpy).not.toHaveBeenCalled()
    })

    it("accepts ordinary image text when SVG markup is not at the beginning", async () => {
      const { container } = render(<MessageInput onSend={() => {}} />)
      const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
      const image = new File(["not-used"], "raster.png", { type: "image/png" })
      const sniffBlob = new Blob([])
      Object.defineProperty(sniffBlob, "text", {
        configurable: true,
        value: vi.fn().mockResolvedValue('PNG header bytes <svg viewBox="0 0 1 1">'),
      })
      vi.spyOn(image, "slice").mockReturnValue(sniffBlob)
      setFiles(fileInput, [image])

      await act(async () => {
        fireEvent.change(fileInput)
      })

      expect(screen.queryByRole("alert")).toBeNull()
      expect(createObjectURLSpy).toHaveBeenCalledWith(image)
    })

    it("does not call onTyping or alter the value when the code-point limit is exceeded", () => {
      const onTyping = vi.fn()
      render(<MessageInput onSend={() => {}} onTyping={onTyping} />)
      const textarea = screen.getByRole("textbox", {
        name: "messenger:typeMessage",
      }) as HTMLTextAreaElement
      const limit = "😀".repeat(32_768)

      fireEvent.change(textarea, { target: { value: limit } })
      fireEvent.change(textarea, { target: { value: `${limit}😀` } })

      expect(textarea.value).toBe(limit)
      expect(onTyping).toHaveBeenCalledTimes(1)
    })

    it("allows the reply cancel control to be clicked when no callback is supplied", () => {
      render(
        <MessageInput
          onSend={() => {}}
          replyingTo={{ senderName: "Alice", isMe: false, text: "quoted" }}
        />
      )
      expect(() =>
        fireEvent.click(screen.getByRole("button", { name: "common:buttons.cancel" }))
      ).not.toThrow()
    })
  })
})
