import type { ComponentPropsWithoutRef, ElementType, ReactNode } from "react"
import { cn } from "@/utils/cn"

type AlertTone = "info" | "success" | "warning" | "error"
type AlertSize = "sm" | "md"

const toneStyles: Record<AlertTone, string> = {
  info: cn(
    "border-[color:color-mix(in_srgb,var(--nav-link)_42%,transparent)]",
    "bg-[color:color-mix(in_srgb,var(--card-bg)_94%,var(--nav-link)_6%)]",
    "text-[color:color-mix(in_srgb,var(--page-text)_90%,var(--nav-link)_10%)]",
    "dark:border-[color:color-mix(in_srgb,var(--nav-link)_48%,transparent)]",
    "dark:bg-[color:color-mix(in_srgb,var(--card-bg)_88%,var(--nav-link)_12%)]",
    "dark:text-[color:color-mix(in_srgb,var(--page-text)_88%,var(--nav-link)_12%)]"
  ),
  success: cn(
    "border-[color:rgba(16,185,129,0.45)]",
    "bg-[rgba(16,185,129,0.14)]",
    "text-[color:rgba(6,95,70,0.92)]",
    "dark:border-[color:rgba(110,231,183,0.5)]",
    "dark:bg-[rgba(17,94,89,0.32)]",
    "dark:text-[color:rgba(167,243,208,0.92)]"
  ),
  warning: cn(
    "border-[color:rgba(250,204,21,0.42)]",
    "bg-[rgba(250,204,21,0.18)]",
    "text-[color:rgba(161,98,7,0.94)]",
    "dark:border-[color:rgba(253,224,71,0.45)]",
    "dark:bg-[rgba(202,138,4,0.28)]",
    "dark:text-[color:rgba(254,249,195,0.9)]"
  ),
  error: cn(
    "border-[color:rgba(248,113,113,0.48)]",
    "bg-[rgba(248,113,113,0.16)]",
    "text-[color:rgba(153,27,27,0.95)]",
    "dark:border-[color:rgba(248,113,113,0.54)]",
    "dark:bg-[rgba(127,29,29,0.32)]",
    "dark:text-[color:rgba(255,228,230,0.95)]"
  ),
}

const sizeStyles: Record<AlertSize, string> = {
  sm: "px-3 py-2 text-[0.87rem] gap-2",
  md: "px-4 py-3 text-[0.95rem] gap-3",
}

type AlertOwnProps = {
  as?: ElementType
  tone?: AlertTone
  size?: AlertSize
  leadingIcon?: ReactNode
  title?: ReactNode
  children?: ReactNode
  role?: "alert" | "status"
  className?: string
}

export type AlertProps<T extends ElementType = "div"> = AlertOwnProps &
  Omit<ComponentPropsWithoutRef<T>, keyof AlertOwnProps>

export const Alert = <T extends ElementType = "div">({
  as,
  tone = "info",
  size = "md",
  leadingIcon,
  title,
  children,
  role = "alert",
  className,
  ...rest
}: AlertProps<T>) => {
  const Component = (as ?? "div") as ElementType

  return (
    <Component
      role={role}
      className={cn(
        "relative flex w-full items-start rounded-ue-lg border font-medium leading-tight",
        sizeStyles[size],
        toneStyles[tone],
        className
      )}
      {...rest}
    >
      {leadingIcon ? (
        <span className="mt-0.5 inline-flex h-5 w-5 flex-shrink-0 items-center justify-center text-current">
          {leadingIcon}
        </span>
      ) : null}
      <div className="flex flex-col gap-1">
        {title ? <span className="text-[0.95rem] font-semibold">{title}</span> : null}
        {children ? <div className="text-[inherit] leading-snug">{children}</div> : null}
      </div>
    </Component>
  )
}

Alert.displayName = "Alert"

