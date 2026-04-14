import { ReactNode } from "react"
import { cn } from "@/utils/cn"

interface EmptyStateProps {
  icon?: ReactNode
  title: string
  description?: string
  action?: ReactNode
  className?: string
}

export function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex w-full max-w-[28rem] flex-col items-center gap-5 rounded-2xl border border-glass-border/(--opacity-soft) bg-(--bg-surface)/(--opacity-medium) px-8 py-14 text-center shadow-glass backdrop-blur-md",
        className
      )}
    >
      {icon && (
        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-brand/(--opacity-subtle) border border-brand/(--opacity-dim) shadow-brand/(--opacity-subtle) shadow-lg text-brand">
          {icon}
        </div>
      )}
      <div className="space-y-2">
        <h3 className="text-lg font-semibold text-text-primary">{title}</h3>
        {description && <p className="text-sm text-(--text-secondary)">{description}</p>}
      </div>
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}
