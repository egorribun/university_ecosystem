import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

const shortcuts = [
  { key: "J", action: "keyboard.next" },
  { key: "K", action: "keyboard.prev" },
  { key: "Enter", action: "keyboard.open" },
  { key: "Esc", action: "keyboard.deselect" },
  { key: "?", action: "keyboard.toggleHelp" },
] as const

export function NewsShortcutsOverlay() {
  const [open, setOpen] = useState(false)
  const { t } = useTranslation(["news"])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable) return
      if (target.closest("dialog, [role='dialog']")) return

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
  }, [open])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-overlay flex items-center justify-center bg-black/(--opacity-strong) backdrop-blur-sm"
      onClick={() => setOpen(false)}
      onKeyDown={(e) => { if (e.key === "Escape") setOpen(false) }}
      role="dialog"
      aria-modal="true"
      aria-label={t("news:keyboard.overlayTitle")}
      tabIndex={-1}
    >
      <div
        className="glass-layer-elevated glass-noise rounded-2xl p-6 sm:p-8 max-w-sm w-full mx-4 shadow-premium-lift"
        role="document"
      >
        <h2 className="text-lg font-bold text-text-primary mb-4">
          {t("news:keyboard.overlayTitle")}
        </h2>
        <dl className="space-y-2.5">
          {shortcuts.map(({ key, action }) => (
            <div key={key} className="flex items-center justify-between">
              <dt className="text-sm text-(--text-secondary)">
                {t(`news:${action}`, { defaultValue: action.split(".").pop() })}
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
          {t("news:keyboard.pressToClose")}
        </p>
      </div>
    </div>
  )
}
