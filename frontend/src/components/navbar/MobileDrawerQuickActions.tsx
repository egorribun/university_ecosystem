import { Search, Bell, Settings } from "lucide-react"
import { cn } from "@/utils/cn"

interface MobileDrawerQuickActionsProps {
  onSearch: () => void
  onNotifications: () => void
  onSettings: () => void
  prefersReducedMotion: boolean
  t: (key: string) => string
}

export function MobileDrawerQuickActions({
  onSearch,
  onNotifications,
  onSettings,
  prefersReducedMotion,
  t,
}: MobileDrawerQuickActionsProps) {
  const actions = [
    { icon: Search, label: t("navigation:menu.search"), onClick: onSearch },
    { icon: Bell, label: t("navigation:menu.notifications"), onClick: onNotifications },
    { icon: Settings, label: t("navigation:menu.settings"), onClick: onSettings },
  ]

  return (
    <div className="flex items-center gap-2 px-4 py-2">
      {actions.map((action) => {
        const Icon = action.icon
        return (
          <button
            key={action.label}
            type="button"
            onClick={action.onClick}
            aria-label={action.label}
            title={action.label}
            className={cn(
              "flex flex-1 items-center justify-center gap-2 rounded-xl py-2.5 px-3",
              "border border-(--glass-border) bg-(--bg-surface-hover)/(--opacity-subtle)",
              "text-(--text-secondary) text-xs font-medium",
              "transition-all hover:bg-(--bg-surface-hover)/(--opacity-dim) hover:text-(--text-primary)",
              prefersReducedMotion ? "duration-0" : "duration-200",
              "cursor-pointer"
            )}
          >
            <Icon size={16} aria-hidden="true" />
            <span className="hidden min-[360px]:inline">{action.label}</span>
          </button>
        )
      })}
    </div>
  )
}
