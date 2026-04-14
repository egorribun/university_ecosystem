import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

const shortcuts = [
  { key: "J", action: "keyboard.next" },
  { key: "K", action: "keyboard.prev" },
  { key: "Enter", action: "keyboard.open" },
  { key: "R", action: "keyboard.register" },
  { key: "Esc", action: "keyboard.deselect" },
  { key: "?", action: "keyboard.toggleHelp" },
] as const

export function EventsShortcutsOverlay() {
  const [open, setOpen] = useState(false)
  const { t } = useTranslation(["events"])
  const triggerRef = useRef<Element | null>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)
        return
      if (target.closest("dialog, [role='dialog']")) return

      if (e.key === "?" && !e.ctrlKey && !e.metaKey) {
        e.preventDefault()
        if (!open) triggerRef.current = document.activeElement
        setOpen((v) => !v)
      }
      if (e.key === "Escape" && open) {
        e.preventDefault()
        setOpen(false)
        // Return focus to trigger element (WCAG 2.4.3)
        setTimeout(() => (triggerRef.current as HTMLElement)?.focus?.(), 0)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [open])

  if (!open) return null

  return (
    // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions, jsx-a11y/click-events-have-key-events -- backdrop overlay, keyboard handled via window listener
    <div
      className="fixed inset-0 z-overlay flex items-center justify-center bg-black/(--opacity-strong) backdrop-blur-sm"
      onClick={() => setOpen(false)}
      role="dialog"
      aria-modal="true"
      aria-label={t("events:keyboard.overlayTitle")}
      tabIndex={-1}
    >
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions, jsx-a11y/click-events-have-key-events -- stopPropagation on content panel */}
      <div
        className="glass-layer-elevated glass-noise rounded-2xl p-6 sm:p-8 max-w-sm w-full mx-4 shadow-premium-lift"
        role="document"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-bold text-text-primary mb-4">
          {t("events:keyboard.overlayTitle")}
        </h2>
        <dl className="space-y-2.5">
          {shortcuts.map(({ key, action }) => (
            <div key={key} className="flex items-center justify-between">
              <dt className="text-sm text-(--text-secondary)">
                {t(`events:${action}`)}
              </dt>
              <dd>
                <kbd className="inline-flex h-7 min-w-7 items-center justify-center rounded-lg glass-layer-surface border border-glass-border/(--opacity-soft) px-2 text-xs font-bold text-text-primary shadow-sm">
                  {key}
                </kbd>
              </dd>
            </div>
          ))}
        </dl>
        <p className="mt-4 text-[11px] text-(--text-secondary)/(--opacity-medium)">
          {t("events:keyboard.pressToClose")}
        </p>
      </div>
    </div>
  )
}
