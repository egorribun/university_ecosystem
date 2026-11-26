import { useEffect, useId, useState } from "react"
import { X } from "lucide-react"
import { useTranslation } from "react-i18next"
import useFocusTrap from "@/hooks/useFocusTrap"

const shortcuts = [
  { key: "J", action: "keyboard.next" },
  { key: "K", action: "keyboard.prev" },
  { key: "Enter", action: "keyboard.open" },
  { key: "Esc", action: "keyboard.deselect" },
  { key: "?", action: "keyboard.toggleHelp" },
] as const

export function NewsShortcutsOverlay() {
  const [open, setOpen] = useState(false)
  const { t } = useTranslation(["news", "common"])
  const titleId = useId()
  const descriptionId = useId()
  const dialogRef = useFocusTrap<HTMLDivElement>({
    active: open,
    escapeDeactivates: false,
  })

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)
        return
      const targetDialog = target.closest("dialog, [role='dialog']")
      if (targetDialog && targetDialog !== dialogRef.current) return

      if (e.key === "?" && !e.ctrlKey && !e.metaKey) {
        e.preventDefault()
        setOpen((v) => !v)
      }
      if (e.key === "Escape" && open) {
        e.preventDefault()
        setOpen(false)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [dialogRef, open])

  if (!open) return null

  return (
    // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions -- backdrop with dialog semantics; Escape key handled for WCAG 2.1 1.4.13
    <div
      ref={dialogRef}
      className="fixed inset-0 z-overlay flex items-center justify-center bg-black/[calc(var(--opacity-strong)*100%)] backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) setOpen(false)
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") setOpen(false)
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      tabIndex={-1}
    >
      <div
        className="glass-layer-elevated glass-noise rounded-2xl p-6 sm:p-8 max-w-sm w-full mx-4 shadow-premium-lift"
        role="document"
      >
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 id={titleId} className="text-lg font-bold text-text-primary">
            {t("news:keyboard.overlayTitle")}
          </h2>
          <button
            type="button"
            onClick={() => setOpen(false)}
            aria-label={t("common:buttons.close")}
            className="inline-flex min-h-[44px] min-w-[44px] shrink-0 items-center justify-center rounded-xl text-text-secondary hover:bg-(--bg-surface-hover) focus-ring-premium"
          >
            <X className="size-5" aria-hidden="true" />
          </button>
        </div>
        <dl className="space-y-2.5">
          {shortcuts.map(({ key, action }) => (
            <div key={key} className="flex items-center justify-between">
              <dt className="text-sm text-(--text-secondary)">
                {t(`news:${action}`, { defaultValue: action.split(".").pop() })}
              </dt>
              <dd>
                <kbd className="inline-flex h-7 min-w-7 items-center justify-center rounded-lg glass-layer-surface border border-glass-border/[calc(var(--opacity-soft)*100%)] px-2 text-xs font-bold text-text-primary shadow-sm">
                  {key}
                </kbd>
              </dd>
            </div>
          ))}
        </dl>
        <p
          id={descriptionId}
          className="mt-4 text-[11px] text-(--text-secondary)/[calc(var(--opacity-medium)*100%)]"
        >
          {t("news:keyboard.pressToClose")}
        </p>
      </div>
    </div>
  )
}
