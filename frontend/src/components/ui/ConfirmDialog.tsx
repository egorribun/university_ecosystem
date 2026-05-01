import { useId } from "react"
import { cn } from "@/utils/cn"
import { AnimatePresence, m } from "framer-motion"

export interface ConfirmDialogProps {
  open: boolean
  title: string
  message: string
  confirmText: string
  cancelText: string
  variant?: "danger" | "warning" | "default"
  onConfirm: () => void
  onCancel: () => void
  isLoading?: boolean
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmText,
  cancelText,
  variant = "default",
  onConfirm,
  onCancel,
  isLoading = false,
}: ConfirmDialogProps) {
  const titleId = useId()
  const messageId = useId()

  return (
    <AnimatePresence>
      {open && (
        <m.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-modal flex items-center justify-center bg-overlay/(--opacity-strong) p-4 backdrop-blur-md"
          role="presentation"
        >
          <m.div
            role="alertdialog"
            aria-modal="true"
            aria-labelledby={titleId}
            aria-describedby={messageId}
            initial={{ scale: 0.9, opacity: 0, y: 20 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.9, opacity: 0, y: 20 }}
            className="w-full max-w-[28rem] overflow-hidden rounded-2xl border border-(--glass-border) bg-(--bg-surface) shadow-premium dark:bg-page"
          >
            <div className="flex flex-col gap-4 p-8">
              <h3 id={titleId} className="sf-pro text-xl font-bold tracking-tight">
                {title}
              </h3>
              <p
                id={messageId}
                className="text-base font-medium leading-relaxed text-text-secondary"
              >
                {message}
              </p>
              <div className="flex justify-end gap-3 pt-4">
                <m.button
                  type="button"
                  whileHover={{ scale: 1.05, backgroundColor: "var(--bg-surface-hover)" }}
                  whileTap={{ scale: 0.95 }}
                  onClick={onCancel}
                  disabled={isLoading}
                  className="rounded-sm border border-subtle px-6 py-3 text-sm font-bold transition-colors focus-ring-premium disabled:opacity-50 disabled:pointer-events-none"
                >
                  {cancelText}
                </m.button>
                <m.button
                  type="button"
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={onConfirm}
                  disabled={isLoading}
                  aria-busy={isLoading}
                  className={cn(
                    "rounded-sm px-6 py-3 text-sm font-bold text-white shadow-surface transition-all focus-ring-premium disabled:opacity-50 disabled:pointer-events-none flex items-center gap-2",
                    variant === "danger"
                      ? "bg-error-text shadow-glow-error"
                      : variant === "warning"
                        ? "bg-warning-text shadow-glow-warning"
                        : "bg-primary-main shadow-glow-primary"
                  )}
                >
                  {isLoading && (
                    <div
                      className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white"
                      aria-hidden="true"
                    />
                  )}
                  {confirmText}
                </m.button>
              </div>
            </div>
          </m.div>
        </m.div>
      )}
    </AnimatePresence>
  )
}
