import { FC, useState, useRef, useEffect, useCallback } from "react"
import {
  MoreVertical as MoreVertIcon,
  Pencil as EditIcon,
  Trash2 as DeleteIcon,
} from "lucide-react"
import { useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"

interface NewsCardActionsProps {
  onEdit: () => void
  onDelete: () => void
  isDisabled?: boolean
  id: string
}

const iconButtonClass =
  "inline-flex h-9 w-9 items-center justify-center rounded-full border border-white/15 bg-white/80 text-(--nav-link) shadow-surface transition hover:bg-white focus-visible:outline-none focus-visible:shadow-focus"

const menuPanelClass =
  "absolute right-0 top-12 z-20 min-w-[180px] overflow-hidden rounded-ue-md border border-white/12 bg-input-mix/98 shadow-surface-strong backdrop-blur-xl"

const menuItemClass =
  "flex w-full items-center gap-2 px-4 py-2.5 text-left text-[0.95rem] font-medium text-(--page-text) transition hover:bg-(--glass-bg)/80 focus-visible:outline-none focus-visible:bg-(--glass-bg)"

export const NewsCardActions: FC<NewsCardActionsProps> = ({ onEdit, onDelete, isDisabled, id }) => {
  const { t } = useTranslation(["news", "common"])
  const [menuOpen, setMenuOpen] = useState(false)
  const menuButtonRef = useRef<HTMLButtonElement | null>(null)
  const menuRef = useRef<HTMLDivElement | null>(null)
  const firstMenuItemRef = useRef<HTMLButtonElement | null>(null)

  const menuId = `news-card-menu-${id}`
  const menuButtonId = `${menuId}-button`

  useEffect(() => {
    if (!menuOpen) return

    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node
      if (menuRef.current?.contains(target) || menuButtonRef.current?.contains(target)) return
      setMenuOpen(false)
    }

    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false)
        menuButtonRef.current?.focus()
      }
    }

    document.addEventListener("mousedown", handleClickOutside)
    document.addEventListener("keydown", handleKey)
    if (firstMenuItemRef.current) firstMenuItemRef.current.focus()

    return () => {
      document.removeEventListener("mousedown", handleClickOutside)
      document.removeEventListener("keydown", handleKey)
    }
  }, [menuOpen])

  const toggleMenu = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    setMenuOpen((prev) => !prev)
  }, [])

  return (
    <div
      className="absolute right-3 top-3 z-10"
      onClick={(e) => e.stopPropagation()}
      role="presentation"
    >
      <button
        ref={menuButtonRef}
        type="button"
        id={menuButtonId}
        aria-label={t("news:aria.cardActions") ?? ""}
        aria-controls={menuOpen ? menuId : undefined}
        aria-haspopup="true"
        aria-expanded={menuOpen ? "true" : undefined}
        className={iconButtonClass}
        onClick={toggleMenu}
        disabled={isDisabled}
        data-news-card-menu-button
      >
        <MoreVertIcon size={20} />
      </button>

      {menuOpen && (
        <div
          ref={menuRef}
          id={menuId}
          role="menu"
          aria-labelledby={menuButtonId}
          data-news-card-menu
          className={menuPanelClass}
        >
          <button
            ref={firstMenuItemRef}
            type="button"
            className={menuItemClass}
            onClick={(e) => {
              e.stopPropagation()
              onEdit()
              setMenuOpen(false)
            }}
          >
            <EditIcon size={16} className="text-(--nav-link)" />
            {t("common:buttons.edit")}
          </button>
          <button
            type="button"
            className={cn(menuItemClass, "text-(--error-text)")}
            onClick={(e) => {
              e.stopPropagation()
              onDelete()
              setMenuOpen(false)
            }}
          >
            <DeleteIcon size={16} className="text-(--error-text)" />
            {t("common:buttons.delete")}
          </button>
        </div>
      )}
    </div>
  )
}
