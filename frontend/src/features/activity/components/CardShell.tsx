import type { ReactNode, CSSProperties } from "react"
import { cn } from "@/utils/cn"

const ACCENT_MAP = {
  neutral: undefined,
  success: "var(--activity-present-accent)",
  info: "var(--activity-grade-accent)",
  warning: "var(--activity-participation-accent)",
} as const

export type CardShellTone = keyof typeof ACCENT_MAP

type CardShellProps = {
  tone?: CardShellTone
  children: ReactNode
  className?: string
  "aria-label"?: string
}

export default function CardShell({
  tone = "neutral",
  children,
  className,
  "aria-label": ariaLabel,
}: CardShellProps) {
  const accent = ACCENT_MAP[tone]

  return (
    <div
      role="group"
      className={cn("activity-card-matte", className)}
      style={accent ? ({ "--_accent": accent } as CSSProperties) : undefined}
      aria-label={ariaLabel}
    >
      <div className="flex h-full w-full flex-col items-stretch rounded-2xl p-4 text-left md:p-6 xl:p-8">
        <div className="flex flex-1 flex-col gap-2">{children}</div>
      </div>
    </div>
  )
}
