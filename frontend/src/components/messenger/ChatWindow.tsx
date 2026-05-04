import React, { useRef, useEffect } from "react"
import { m } from "framer-motion" // Removed AnimatePresence, LayoutGroup as they are not used
import { File, Check, CheckCheck } from "lucide-react"
import { useVirtualizer } from "@tanstack/react-virtual"
import { useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"
import SmartImage from "@/components/media/SmartImage"
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders"
import { sanitizeUrl } from "@/utils/media"
import { Message } from "./types"

interface ChatWindowProps {
  messages: Message[]
}

// PERF-27-02: Removed React.memo() — React Compiler "infer" mode handles memoization
export const ChatWindow: React.FC<ChatWindowProps> = ({ messages }) => {
  const { t } = useTranslation()
  const containerRef = useRef<HTMLDivElement>(null)

  const virtualizer = useVirtualizer({
    count: messages.length,
    getScrollElement: () => containerRef.current,
    estimateSize: () => 80,
    overscan: 5,
  })

  const prevMessagesLengthRef = useRef(0)

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (messages.length > prevMessagesLengthRef.current) {
      virtualizer.scrollToIndex(messages.length - 1, { align: "end", behavior: "auto" })
    }
    prevMessagesLengthRef.current = messages.length
  }, [messages.length, virtualizer])

  // Initial scroll to bottom
  useEffect(() => {
    if (messages.length > 0) {
      virtualizer.scrollToIndex(messages.length - 1, { align: "end", behavior: "auto" })
    }
  }, [messages.length, virtualizer])

  return (
    <div
      ref={containerRef}
      role="log"
      aria-live="polite"
      aria-label={t("messenger:aria.messageList")}
      className="msg-chat-area flex-1 min-h-0 overflow-y-auto p-4 custom-scrollbar"
    >
      <div
        style={{
          height: `${virtualizer.getTotalSize()}px`,
          width: "100%",
          position: "relative",
        }}
      >
        {virtualizer.getVirtualItems().map((virtualRow) => {
          const message = messages[virtualRow.index]
          if (!message) return null

          return (
            <div
              key={virtualRow.key}
              ref={virtualizer.measureElement}
              data-index={virtualRow.index}
              className="absolute top-0 left-0 w-full"
              style={{
                transform: `translateY(${virtualRow.start}px)`,
              }}
            >
              <m.div
                initial={{ opacity: 0, y: 10, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
                className={cn(
                  "flex items-end gap-2 md:gap-3 py-1 w-full md:flex-row group",
                  message.isMe
                    ? "flex-row-reverse justify-start md:justify-start"
                    : "flex-row justify-start"
                )}
              >
                <div className="shrink-0 mb-1">
                  <SmartImage
                    srcRaw={message.senderAvatar || AVATAR_PLACEHOLDER_URL}
                    fallback={AVATAR_PLACEHOLDER_URL}
                    alt={message.senderName || ""}
                    className="w-8 h-8 md:w-9 md:h-9 rounded-full object-cover shadow-sm ring-1 ring-black/(--opacity-faint) dark:ring-white/(--opacity-faint)"
                  />
                </div>

                <div
                  className={cn(
                    "max-w-4/5 md:max-w-3/4 px-4 py-2.5 text-base relative",
                    message.isMe
                      ? "msg-bubble-sent text-white rounded-2xl rounded-br-sm md:rounded-br-2xl md:rounded-bl-sm"
                      : "msg-bubble-received text-text-primary rounded-2xl rounded-bl-sm shadow-sm"
                  )}
                >
                  {message.attachments && message.attachments.length > 0 && (
                    <div className="mb-2 space-y-2">
                      {message.attachments.map((attachment) => (
                        <div key={attachment.id} className="overflow-hidden rounded-xl">
                          {attachment.type === "image" ? (
                            sanitizeUrl(attachment.url) ? (
                              <SmartImage
                                srcRaw={attachment.url}
                                alt={attachment.name}
                                className="w-full h-auto max-h-72 object-cover cursor-pointer hover:scale-hover transition-transform duration-slow"
                                onClick={() => {
                                  const safe = sanitizeUrl(attachment.url)
                                  if (safe) window.open(safe, "_blank", "noopener,noreferrer")
                                }}
                              />
                            ) : null
                          ) : sanitizeUrl(attachment.url) ? (
                            <a
                              href={sanitizeUrl(attachment.url)!}
                              target="_blank"
                              rel="noopener noreferrer"
                              className={cn(
                                "flex items-center gap-3 p-3 rounded-xl transition-colors border border-white/(--opacity-faint)",
                                message.isMe
                                  ? "bg-white/(--opacity-subtle) hover:bg-white/(--opacity-soft)"
                                  : "bg-(--bg-surface-raised)/(--opacity-medium) hover:bg-(--bg-surface-hover)/(--opacity-medium)"
                              )}
                            >
                              <div className="p-2 rounded-lg bg-white/(--opacity-subtle) text-(--brand-main)">
                                <File size={20} />
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className="truncate text-sm font-bold">{attachment.name}</p>
                                <p className="text-micro opacity-medium font-medium">
                                  {(attachment.size / 1024).toFixed(1)} KB
                                </p>
                              </div>
                            </a>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  )}
                  <p className="wrap-break-word leading-relaxed whitespace-pre-wrap">
                    {message.text}
                  </p>
                  <div className="flex items-center justify-end gap-1.5 mt-(--space-1) opacity-hover">
                    <span
                      className="text-micro font-bold uppercase tracking-wider"
                      style={{
                        color: message.isMe ? "var(--primary-subtle)" : "var(--text-secondary)",
                      }}
                    >
                      {message.timestamp}
                    </span>
                    {message.isMe && (
                      <span className="flex items-center opacity-hover">
                        {message.status === "read" ? (
                          <CheckCheck className="w-3 h-3 text-white" />
                        ) : (
                          <Check className="w-3 h-3 text-white opacity-medium" />
                        )}
                      </span>
                    )}
                  </div>
                </div>
              </m.div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

ChatWindow.displayName = "ChatWindow"
