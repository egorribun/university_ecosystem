import React, { useEffect, useRef, useState } from "react"
import { m, AnimatePresence, useReducedMotion } from "framer-motion"
import { useTranslation } from "react-i18next"
import { X, FileText, Image as ImageIcon, File, Paperclip, Send } from "lucide-react"
import { cn } from "@/utils/cn"
import SmartImage from "@/components/media/SmartImage"

interface MessageInputProps {
  onSend: (text: string, files: File[]) => void
}

// Wave 183 SW7 — extended selectedFiles tuple from {id, file} to
// {id, file, previewUrl}. Pre-W183 the JSX called `URL.createObjectURL(file)`
// INLINE in the SmartImage `srcRaw` prop, which created a NEW Blob URL on
// every parent re-render (user typing in textarea triggers parent setState
// → re-render → new URL per attachment). Each created URL persisted in the
// browser URL table until tab close. With multi-image attachments + heavy
// keystroke activity, this could leak hundreds of KB of native Blob memory.
// Now createObjectURL fires ONCE per file at handleFileSelect time;
// revokeObjectURL fires on removeFile + on send (mutation handler in
// useMessengerController already revokes its own optimistic URLs) + on
// unmount.
interface SelectedFile {
  id: string
  file: File
  previewUrl: string
}

export const MessageInput: React.FC<MessageInputProps> = ({ onSend }) => {
  const { t } = useTranslation(["messenger"])
  const [text, setText] = useState("")
  const [showAttachMenu, setShowAttachMenu] = useState(false)
  // Wave 182 SW2 — selectedFiles tracks each File with a stable UUID
  // (was File[]; composite key `${name}-${size}-${index}` collided when
  // the user added two copies of the same file). UUIDs make removal +
  // React reconciliation deterministic regardless of duplicates.
  // Wave 183 SW7 — extended with `previewUrl` for Blob URL lifetime mgmt.
  const [selectedFiles, setSelectedFiles] = useState<SelectedFile[]>([])
  const [svgRejected, setSvgRejected] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Wave 183 SW7 — mirror selectedFiles into a ref so the unmount cleanup
  // can revoke outstanding Blob URLs without relying on the setState
  // updater fn (which React does NOT invoke during component unmount —
  // setState calls after unmount are batched + dropped). Without this
  // ref, the unmount-cleanup branch would be a no-op + URLs leak.
  const selectedFilesRef = useRef<SelectedFile[]>(selectedFiles)
  useEffect(() => {
    selectedFilesRef.current = selectedFiles
  }, [selectedFiles])

  useEffect(() => {
    return () => {
      selectedFilesRef.current.forEach((entry) => URL.revokeObjectURL(entry.previewUrl))
    }
  }, [])
  // Wave 181 SW3 — useReducedMotion guard for attach + send button micro-interactions.
  const prefersReducedMotion = useReducedMotion() ?? false
  const attachHoverAnim = prefersReducedMotion ? undefined : { scale: 1.1 }
  const attachTapAnim = prefersReducedMotion ? undefined : { scale: 0.9 }
  const sendCanFire = text.trim().length > 0 || selectedFiles.length > 0
  const sendHoverAnim = prefersReducedMotion || !sendCanFire ? undefined : { scale: 1.08 }
  const sendTapAnim = prefersReducedMotion || !sendCanFire ? undefined : { scale: 0.92 }

  const handleSend = () => {
    if (text.trim() || selectedFiles.length > 0) {
      onSend(
        text,
        selectedFiles.map((entry) => entry.file)
      )
      // Wave 183 SW7 — revoke Blob URLs when files are handed off to send.
      // useMessengerController creates its own optimistic-message URLs at
      // mutation time; the preview URLs here are no longer needed once the
      // files leave MessageInput's scope.
      selectedFiles.forEach((entry) => URL.revokeObjectURL(entry.previewUrl))
      setText("")
      setSelectedFiles([])
      setShowAttachMenu(false)
    }
  }

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault()
      handleSend()
    }
  }

  const handleAttachmentClick = (type: "photo" | "file" | "document") => {
    setShowAttachMenu(false)
    if (fileInputRef.current) {
      switch (type) {
        case "photo":
          fileInputRef.current.accept = "image/png,image/jpeg,image/gif,image/webp"
          break
        case "document":
          fileInputRef.current.accept = ".pdf,.doc,.docx,.txt"
          break
        case "file":
          fileInputRef.current.accept = "*"
          break
      }
      fileInputRef.current.click()
    }
  }

  const handleFileSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files
    if (files && files.length > 0) {
      const filteredFiles = await Promise.all(
        Array.from(files).map(async (file) => {
          if (file.type === "image/svg+xml" || file.name.toLowerCase().endsWith(".svg")) {
            return null
          }
          if (file.type.startsWith("image/")) {
            try {
              const fileText = await file.slice(0, 512).text()
              // eslint-disable-next-line security/detect-unsafe-regex -- bounded 512-byte input, no ReDoS risk
              if (/^\s*(<\?xml[^>]*>\s*)?<svg[\s>]/i.test(fileText)) return null
            } catch {
              // ignore
            }
          }
          return file
        })
      )
      const validFiles = filteredFiles.filter((file): file is File => !!file)
      const rejectedCount = filteredFiles.length - validFiles.length
      if (rejectedCount > 0) {
        setSvgRejected(true)
        setTimeout(() => setSvgRejected(false), 3000)
      }
      setSelectedFiles((previousFiles) => [
        ...previousFiles,
        // Wave 183 SW7 — create Blob URL ONCE per file at add time.
        // Pre-W183 the JSX created a new URL on every parent re-render
        // (memory leak).
        ...validFiles.map((file) => ({
          id: crypto.randomUUID(),
          file,
          previewUrl: URL.createObjectURL(file),
        })),
      ])
    }
    if (fileInputRef.current) fileInputRef.current.value = ""
  }

  const removeFile = (id: string) => {
    // Wave 183 SW7 — revoke Blob URL when the file is removed from the
    // attachment preview. Prevents accumulation of orphaned URLs in the
    // browser table.
    setSelectedFiles((prev) => {
      const removed = prev.find((entry) => entry.id === id)
      if (removed) URL.revokeObjectURL(removed.previewUrl)
      return prev.filter((entry) => entry.id !== id)
    })
  }

  return (
    <div className="shrink-0 p-3 z-popover relative border-t border-glass-border bg-surface/(--opacity-soft) backdrop-blur-xl">
      <AnimatePresence>
        {svgRejected && (
          <m.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            className="absolute -top-10 left-3 right-3 rounded-lg bg-error-bg px-3 py-1.5 text-sm text-error-text shadow-sm"
            role="alert"
          >
            {t("messenger:svgNotAllowed")}
          </m.div>
        )}
      </AnimatePresence>
      {selectedFiles.length > 0 && (
        <div className="flex gap-2 mb-3 overflow-x-auto pb-2 custom-scrollbar">
          {selectedFiles.map(({ id, file, previewUrl }) => (
            <div key={id} className="relative shrink-0 group">
              {file.type.startsWith("image/") ? (
                // Wave 183 SW7 — use pre-computed previewUrl from state
                // (created ONCE per file in handleFileSelect) instead of
                // calling URL.createObjectURL inline per render. Prevents
                // memory leak from re-renders triggered by user typing in
                // the textarea.
                <SmartImage
                  srcRaw={previewUrl}
                  alt={file.name}
                  className="w-16 h-16 object-cover rounded-xl border border-(--glass-border)/(--opacity-dim) shadow-sm"
                />
              ) : (
                <div className="shrink-0 flex items-center justify-center h-10 w-10 md:h-12 md:w-12 bg-(--bg-surface-raised) rounded-xl border border-(--glass-border)/(--opacity-dim) shadow-sm text-(--text-secondary)">
                  <FileText size={32} />
                </div>
              )}
              {/* Wave 183 SW4 — bumped touch target 24×24px → 32×32px visual
                  with 44×44px hit area via `::after { inset: -6px }` (matches
                  W111 CQ-111-04 pattern for visually-small interactive
                  controls). WCAG 2.5.8 Target Size (Enhanced) requires ≥44px
                  for AAA OR ≥24px for AA + sufficient spacing — 32px visual
                  with 44px effective hit area satisfies both. The before
                  bumped also moves the X icon slightly inward (size 12 →
                  14) for better visual proportion. */}
              <button
                type="button"
                onClick={() => removeFile(id)}
                className="absolute -top-1.5 -right-1.5 size-8 bg-(--error-text) text-[var(--text-inverse)] rounded-full flex items-center justify-center shadow-lg hover:bg-(--error-text)/(--opacity-hover) transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500) focus-visible:ring-offset-2 focus-visible:ring-offset-(--bg-surface) after:absolute after:inset-[-6px] after:content-['']"
                aria-label={t("messenger:aria.removeAttachment")}
              >
                <X size={14} strokeWidth={3} aria-hidden="true" />
              </button>
            </div>
          ))}
        </div>
      )}
      <div className="flex items-end gap-2 bg-(--bg-surface-hover)/(--opacity-subtle) rounded-2xl border border-(--glass-border)/(--opacity-dim) p-2 focus-within:ring-4 focus-within:ring-(--brand-main)/(--opacity-faint) focus-within:border-(--brand-main)/(--opacity-dim) transition-all duration-base">
        <div className="relative">
          <m.button
            id="chat-attach-btn"
            type="button"
            whileHover={attachHoverAnim}
            whileTap={attachTapAnim}
            onClick={() => setShowAttachMenu(!showAttachMenu)}
            className={cn(
              "min-h-[44px] min-w-[44px] p-2.5 rounded-xl transition-colors hover:bg-(--bg-surface-hover)/(--opacity-soft)",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500) focus-visible:ring-offset-2 focus-visible:ring-offset-(--bg-surface)",
              showAttachMenu
                ? "text-(--brand-main) bg-(--brand-main)/(--opacity-subtle)"
                : "text-(--text-secondary)"
            )}
            aria-label={t("messenger:aria.attachments")}
          >
            <Paperclip
              size={20}
              className={cn("transition-transform duration-base", showAttachMenu && "rotate-45")}
            />
          </m.button>

          <AnimatePresence>
            {showAttachMenu && (
              <m.div
                initial={{ opacity: 0, scale: 0.95, y: 10 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 10 }}
                className="absolute bottom-full left-0 mb-4 py-2 min-w-(--min-w-column) bg-(--bg-surface)/(--opacity-heavy) backdrop-blur-2xl rounded-2xl border border-(--glass-border) shadow-premium overflow-hidden ring-1 ring-black/(--opacity-faint)"
              >
                {(
                  [
                    {
                      id: "photo",
                      icon: ImageIcon,
                      labelKey: "messenger:attachPhoto",
                      color: "text-(--primary-main) bg-(--primary-main)/(--opacity-subtle)",
                    },
                    {
                      id: "document",
                      icon: FileText,
                      labelKey: "messenger:attachDocument",
                      color: "text-(--success-text) bg-(--success-text)/(--opacity-subtle)",
                    },
                    {
                      id: "file",
                      icon: File,
                      labelKey: "messenger:attachFile",
                      color: "text-(--warning-text) bg-(--warning-text)/(--opacity-subtle)",
                    },
                  ] as const
                ).map((item) => (
                  <button
                    id={`chat-attach-type-${item.id}`}
                    key={item.id}
                    onClick={() => handleAttachmentClick(item.id)}
                    className="w-full px-4 py-3 flex items-center gap-3 hover:bg-(--bg-surface-hover) transition-colors text-left group"
                  >
                    <div
                      className={cn(
                        "w-8 h-8 rounded-lg flex items-center justify-center transition-transform group-hover:scale-110",
                        item.color
                      )}
                    >
                      <item.icon size={18} />
                    </div>
                    <span className="text-sm font-bold text-text-primary">{t(item.labelKey)}</span>
                  </button>
                ))}
              </m.div>
            )}
          </AnimatePresence>

          <input ref={fileInputRef} type="file" className="hidden" onChange={handleFileSelect} />
        </div>
        {/* Wave 183 SW4 — added explicit aria-label. Placeholder alone is
            insufficient for screen-reader announcement (A11Y-114-04 pattern;
            placeholder text disappears on focus + many SR engines treat it
            as supplementary not primary label). Matches W116 SW3 pattern
            for all textareas in messenger. */}
        <textarea
          id="chat-message-input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={t("messenger:typeMessage")}
          aria-label={t("messenger:typeMessage")}
          className="flex-1 bg-transparent border-none focus:ring-0 outline-none resize-none max-h-48 py-2 md:py-2.5 px-1 text-base text-text-primary placeholder:text-(--text-secondary) placeholder:opacity-medium"
          rows={1}
        />
        <m.button
          id="chat-send-btn"
          type="button"
          whileHover={sendHoverAnim}
          whileTap={sendTapAnim}
          onClick={handleSend}
          disabled={!sendCanFire}
          aria-label={t("messenger:aria.sendMessage")}
          className={cn(
            "min-h-[44px] min-w-[44px] p-2.5 rounded-xl transition-all duration-base",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-violet-500) focus-visible:ring-offset-2 focus-visible:ring-offset-(--bg-surface)",
            sendCanFire
              ? "messenger-send-btn"
              : "bg-(--bg-surface-hover)/(--opacity-subtle) text-(--text-secondary) opacity-soft cursor-not-allowed"
          )}
        >
          <Send size={20} fill="currentColor" />
        </m.button>
      </div>
    </div>
  )
}
