import { type FC } from "react"
import {
  MoreVertical as MoreVertIcon,
  Pencil as EditIcon,
  Trash2 as DeleteIcon,
} from "lucide-react"
import { useTranslation } from "react-i18next"
import { ActionMenu } from "@/components/ui/ActionMenu"

interface NewsCardActionsProps {
  onEdit: () => void
  onDelete: () => void
  isDisabled?: boolean
  id: string
}

const iconButtonClass =
  "border border-glass-border-subtle bg-glass-elevated text-(--primary-main) shadow-surface transition hover:bg-surface focus-ring-premium"

const menuPanelClass =
  "absolute right-0 top-12 z-dropdown min-w-(--min-w-field) overflow-hidden rounded-lg border border-glass-border-subtle bg-input-mix/(--opacity-heavy) shadow-surface-strong backdrop-blur-xl"

export const NewsCardActions: FC<NewsCardActionsProps> = ({ onEdit, onDelete, isDisabled, id }) => {
  const { t } = useTranslation(["news", "common"])
  const menuId = `news-card-menu-${id}`
  const menuButtonId = `${menuId}-button`

  return (
    <div
      className="absolute right-3 top-3 z-decor"
      onClick={(e) => e.stopPropagation()}
      role="presentation"
    >
      <ActionMenu
        ariaLabel={t("news:aria.cardActions") ?? ""}
        triggerId={menuButtonId}
        menuId={menuId}
        disabled={isDisabled}
        autoFocusFirstItem
        trigger={<MoreVertIcon size={20} />}
        triggerClassName={iconButtonClass}
        menuClassName={menuPanelClass}
        triggerDataAttributes={{ "data-news-card-menu-button": "true" }}
        menuDataAttributes={{ "data-news-card-menu": "true" }}
        items={[
          {
            label: t("common:buttons.edit"),
            icon: <EditIcon size={16} className="text-(--primary-main)" />,
            onClick: onEdit,
          },
          {
            label: t("common:buttons.delete"),
            icon: <DeleteIcon size={16} className="text-(--error-text)" />,
            onClick: onDelete,
            variant: "danger",
          },
        ]}
      />
    </div>
  )
}
