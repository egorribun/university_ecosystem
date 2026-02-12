import React from "react"
import { Button } from "@/components/ui"
import {
  MoreVertical as MoreVertIcon,
  Pencil as EditIcon,
  Trash2 as DeleteIcon,
} from "lucide-react"
import { useTranslation } from "react-i18next"

interface EventAdminActionsProps {
  menuAnchor: HTMLElement | null
  setMenuAnchor: (anchor: HTMLElement | null) => void
  onEdit: () => void
  onDelete: () => void
  menuId: string
}

export const EventAdminActions: React.FC<EventAdminActionsProps> = ({
  menuAnchor,
  setMenuAnchor,
  onEdit,
  onDelete,
  menuId,
}) => {
  const { t } = useTranslation(["events", "common"])

  return (
    <>
      <Button
        variant="glass"
        size="sm"
        aria-label={t("events:card.aria.actions")}
        aria-controls={menuAnchor ? menuId : undefined}
        aria-haspopup="true"
        aria-expanded={Boolean(menuAnchor)}
        className="absolute top-3 right-3 z-(--z-decor) min-h-0! p-2! rounded-full"
        onClick={(e) => {
          e.stopPropagation()
          setMenuAnchor(e.currentTarget as HTMLElement)
        }}
      >
        <MoreVertIcon size={20} />
      </Button>
      {menuAnchor && (
        <div
          className="absolute right-0 top-12 z-(--z-navbar) min-w-(--min-w-dropdown) rounded-xl border border-(--glass-border) bg-(--bg-surface) shadow-surface-strong"
          onClick={(e) => e.stopPropagation()}
          role="presentation"
        >
          <div className="py-1">
            <button
              type="button"
              className="flex w-full items-center gap-2 px-4 py-2 text-sm text-(--text-primary) transition-colors hover:bg-(--glass-bg)/(--opacity-heavy)"
              onClick={() => {
                setMenuAnchor(null)
                onEdit()
              }}
            >
              <EditIcon size={16} />
              {t("common:buttons.edit")}
            </button>
            <button
              type="button"
              className="flex w-full items-center gap-2 px-4 py-2 text-sm text-(--text-primary) transition-colors hover:bg-(--glass-bg)/(--opacity-heavy)"
              onClick={() => {
                setMenuAnchor(null)
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
