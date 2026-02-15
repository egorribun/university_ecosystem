import React, { useRef, useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { useTranslation } from "react-i18next"
import { X, FileText, Image as ImageIcon, File, Paperclip, Send } from "lucide-react"
import { cn } from "@/utils/cn"
import SmartImage from "@/components/SmartImage"

interface MessageInputProps {
  onSend: (text: string, files: File[]) => void
}

export const MessageInput: React.FC<MessageInputProps> = ({ onSend }) => {
  const { t } = useTranslation(["messenger"])
  const [text, setText] = useState("")
  const [showAttachMenu, setShowAttachMenu] = useState(false)
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleSend = () => {
    if (text.trim() || selectedFiles.length > 0) {
      onSend(text, selectedFiles)
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
              if (/^\s*(<\?xml[^>]*>\s*)?<svg[\s>]/i.test(fileText)) return null
            } catch {
              // ignore
            }
          }
          return file
        })
      )
      setSelectedFiles((previousFiles) => [
        ...previousFiles,
        ...filteredFiles.filter((file) => !!file),
      ])
    }
    if (fileInputRef.current) fileInputRef.current.value = ""
  }

  const removeFile = (index: number) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index))
  }

  return (
    <div className="shrink-0 p-(--space-3) z-popover relative border-t border-(--glass-border)/(--opacity-subtle) bg-(--bg-surface)/(--opacity-soft) backdrop-blur-xl">
      {selectedFiles.length > 0 && (
        <div className="flex gap-2 mb-3 overflow-x-auto pb-2 custom-scrollbar">
          {selectedFiles.map((file, index) => (
            <div key={index} className="relative shrink-0 group">
              {file.type.startsWith("image/") ? (
                <SmartImage
                  srcRaw={URL.createObjectURL(file)}
                  alt={file.name}
                  className="w-16 h-16 object-cover rounded-xl border border-(--glass-border)/(--opacity-dim) shadow-sm"
                />
              ) : (
                <div className="shrink-0 flex items-center justify-center h-10 w-10 md:h-12 md:w-12 bg-(--bg-surface-raised) rounded-xl border border-(--glass-border)/(--opacity-dim) shadow-sm text-(--text-secondary)">
                  <FileText size={32} />
                </div>
              )}
              <button
                onClick={() => removeFile(index)}
                className="absolute -top-1.5 -right-1.5 bg-(--error-text) text-white rounded-full p-1 shadow-lg hover:bg-(--error-text)/(--opacity-hover) transition-colors"
                aria-label="Remove"
              >
                <X size={12} strokeWidth={3} />
              </button>
            </div>
          ))}
        </div>
      )}
      <div className="flex items-end gap-2 bg-(--bg-surface-hover)/(--opacity-subtle) rounded-2xl border border-(--glass-border)/(--opacity-dim) p-2 focus-within:ring-4 focus-within:ring-(--brand-main)/(--opacity-faint) focus-within:border-(--brand-main)/(--opacity-dim) transition-all duration-base">
        <div className="relative">
          <motion.button
            id="chat-attach-btn"
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.9 }}
            onClick={() => setShowAttachMenu(!showAttachMenu)}
            className={cn(
              "p-2.5 rounded-xl transition-colors hover:bg-(--bg-surface-hover)/(--opacity-soft)",
              showAttachMenu
                ? "text-(--brand-main) bg-(--brand-main)/(--opacity-subtle)"
                : "text-(--text-secondary)"
            )}
            aria-label="Attachments"
          >
            <Paperclip
              size={20}
              className={cn("transition-transform duration-base", showAttachMenu && "rotate-45")}
            />
          </motion.button>

          <AnimatePresence>
            {showAttachMenu && (
              <motion.div
                initial={{ opacity: 0, scale: 0.95, y: 10 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 10 }}
                className="absolute bottom-full left-0 mb-4 py-2 min-w-(--min-w-column) bg-(--bg-surface)/(--opacity-heavy) backdrop-blur-2xl rounded-2xl border border-(--glass-border) shadow-premium overflow-hidden ring-1 ring-black/(--opacity-faint)"
              >
                {[
                  {
                    id: "photo",
                    icon: ImageIcon,
                    label: "Photo",
                    color: "text-(--primary-main) bg-(--primary-main)/(--opacity-subtle)",
                  },
                  {
                    id: "document",
                    icon: FileText,
                    label: "Document",
                    color: "text-(--success-text) bg-(--success-text)/(--opacity-subtle)",
                  },
                  {
                    id: "file",
                    icon: File,
                    label: "File",
                    color: "text-(--warning-text) bg-(--warning-text)/(--opacity-subtle)",
                  },
                ].map((item) => (
                  <button
                    id={`chat-attach-type-${item.id}`}
                    key={item.id}
                    onClick={() => handleAttachmentClick(item.id as "photo" | "document" | "file")}
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
                    <span className="text-sm font-bold text-(--text-primary)">
                      {t(`messenger:attach${item.label}`)}
                    </span>
                  </button>
                ))}
              </motion.div>
            )}
          </AnimatePresence>

          <input ref={fileInputRef} type="file" className="hidden" onChange={handleFileSelect} />
        </div>
        <textarea
          id="chat-message-input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={t("messenger:typeMessage", "Message...")}
          className="flex-1 bg-transparent border-none focus:ring-0 outline-none resize-none max-h-48 py-2 md:py-2.5 px-1 text-base text-(--text-primary) placeholder:text-(--text-secondary) placeholder:opacity-medium"
          rows={1}
        />
        <motion.button
          id="chat-send-btn"
          whileHover={text.trim() || selectedFiles.length > 0 ? { scale: 1.1 } : {}}
          whileTap={text.trim() || selectedFiles.length > 0 ? { scale: 0.9 } : {}}
          onClick={handleSend}
          disabled={!text.trim() && selectedFiles.length === 0}
          className={cn(
            "p-2.5 rounded-xl transition-all duration-base",
            text.trim() || selectedFiles.length > 0
              ? "bg-(--brand-main) text-white shadow-lg shadow-(--brand-main)/(--opacity-soft)"
              : "bg-(--bg-surface-hover)/(--opacity-subtle) text-(--text-secondary) opacity-soft cursor-not-allowed"
          )}
        >
          <Send size={20} fill="currentColor" />
        </motion.button>
      </div>
    </div>
  )
}
