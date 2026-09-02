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
    <div className="grid grid-cols-3 gap-2 px-3 py-2">
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
              "flex flex-col items-center justify-center gap-1 rounded-xl py-3 px-1",
              "border border-(--glass-border) bg-(--bg-surface-hover)/(--opacity-subtle)",
              "text-(--text-primary) text-[11px] font-medium leading-tight",
              "transition-[transform,opacity,background-color] hover:bg-(--bg-surface-hover)/(--opacity-dim)",
              prefersReducedMotion ? "duration-0" : "duration-200",
              "cursor-pointer",
              !prefersReducedMotion && "active:scale-[0.97]"
            )}
          >
            <span
              className="flex shrink-0 items-center justify-center rounded-lg p-1.5"
              style={{ backgroundColor: "var(--quick-action-icon-bg)" }}
            >
              <Icon size={16} aria-hidden="true" />
            </span>
            <span className="text-center">{action.label}</span>
          </button>
        )
      })}
    </div>
  )
}
