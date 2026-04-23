import { ReactNode } from "react"
import { cn } from "@/utils/cn"

interface EmptyStateProps {
  icon?: ReactNode
  title: string
  description?: string
  action?: ReactNode
  className?: string
  /**
   * Heading level for the title. Defaults to "h2" so empty states under a page
   * `<h1>` (News, Events, Schedule) keep a valid sequential heading order for
   * WCAG 2.4.6 + Lighthouse heading-order audit. Wave 116 SW3.
   */
  titleAs?: "h2" | "h3" | "h4"
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
  titleAs: TitleTag = "h2",
}: EmptyStateProps) {
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
        <TitleTag className="text-lg font-semibold text-text-primary">{title}</TitleTag>
        {description && <p className="text-sm text-(--text-secondary)">{description}</p>}
      </div>
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}
