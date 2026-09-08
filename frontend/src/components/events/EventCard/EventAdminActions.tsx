import { Button } from "@/components/ui"
import {
  MoreVertical as MoreVertIcon,
  Pencil as EditIcon,
  Trash2 as DeleteIcon,
} from "lucide-react"
import { useCallback, useEffect, useRef, type KeyboardEvent } from "react"
import { useTranslation } from "react-i18next"

interface EventAdminActionsProps {
  menuAnchor: HTMLElement | null
  setMenuAnchor: (anchor: HTMLElement | null) => void
  onEdit: () => void
  onDelete: () => void
  menuId: string
  disabled?: boolean
}

export function EventAdminActions({
  menuAnchor,
  setMenuAnchor,
  onEdit,
  onDelete,
  menuId,
  disabled = false,
}: EventAdminActionsProps) {
  const { t } = useTranslation(["events", "common"])
  const triggerRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const triggerId = `${menuId}-button`
  const menuOpen = Boolean(menuAnchor) && !disabled

  const closeMenu = useCallback(() => {
    setMenuAnchor(null)
    triggerRef.current?.focus()
  }, [setMenuAnchor])

  useEffect(() => {
    if (!menuAnchor) return
    if (disabled) {
      setMenuAnchor(null)
      return
    }
    menuRef.current?.querySelector<HTMLButtonElement>("[role='menuitem']:not(:disabled)")?.focus()
  }, [disabled, menuAnchor, setMenuAnchor])

  useEffect(() => {
    if (!menuOpen) return
    const handleOutsidePointer = (event: globalThis.MouseEvent) => {
      const target = event.target
      if (!(target instanceof Node)) return
      if (triggerRef.current?.contains(target) || menuRef.current?.contains(target)) return
      closeMenu()
    }
    document.addEventListener("mousedown", handleOutsidePointer)
    return () => document.removeEventListener("mousedown", handleOutsidePointer)
  }, [closeMenu, menuOpen])

  const handleMenuKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    event.stopPropagation()
    if (event.key === "Escape") {
      event.preventDefault()
      closeMenu()
      return
    }
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return
    event.preventDefault()
    // The handler is mounted on the same menu node that owns this ref, so a
    // keyboard event cannot reach it before the ref is attached.
    const items = Array.from(
      menuRef.current!.querySelectorAll<HTMLButtonElement>("[role='menuitem']:not(:disabled)")
    )
    if (items.length === 0) return
    const currentIndex = items.indexOf(document.activeElement as HTMLButtonElement)
    const delta = event.key === "ArrowDown" ? 1 : -1
    const nextIndex = (currentIndex + delta + items.length) % items.length
    items[nextIndex]?.focus()
  }

  return (
    <>
      <Button
        ref={triggerRef}
        id={triggerId}
        variant="glass"
        size="sm"
        disabled={disabled}
        aria-label={t("events:card.aria.actions")}
        aria-controls={menuOpen ? menuId : undefined}
        aria-haspopup="menu"
        aria-expanded={menuOpen}
        className="absolute top-3 right-3 z-decor min-h-11 min-w-11 p-2! rounded-full"
        onClick={(e) => {
          e.stopPropagation()
          if (menuAnchor) closeMenu()
          else setMenuAnchor(e.currentTarget as HTMLElement)
        }}
      >
        <MoreVertIcon size={20} />
      </Button>
      {menuOpen && (
        <div
          ref={menuRef}
          id={menuId}
          aria-labelledby={triggerId}
          className="absolute right-0 top-12 z-navbar min-w-(--min-w-dropdown) rounded-xl border border-(--glass-border) bg-(--bg-surface) shadow-surface-strong"
          onClick={(e) => e.stopPropagation()}
          onKeyDown={handleMenuKeyDown}
          role="menu"
          tabIndex={-1}
        >
          <div className="py-1">
            <button
              type="button"
              role="menuitem"
              className="flex min-h-11 w-full items-center gap-2 px-4 py-2 text-sm text-text-primary transition-colors hover:bg-(--glass-bg)/(--opacity-heavy)"
              onClick={() => {
                closeMenu()
                onEdit()
              }}
            >
              <EditIcon size={16} />
              {t("common:buttons.edit")}
            </button>
            <button
              type="button"
              role="menuitem"
              className="flex min-h-11 w-full items-center gap-2 px-4 py-2 text-sm text-text-primary transition-colors hover:bg-(--glass-bg)/(--opacity-heavy)"
              onClick={() => {
                closeMenu()
                onDelete()
              }}
            >
              <DeleteIcon size={16} />
              {t("common:buttons.delete")}
            </button>
          </div>
        </div>
      )}
    </>
  )
}
