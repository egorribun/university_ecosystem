import React, { useEffect } from "react"
import { Loader2 } from "lucide-react"
import { cn } from "@/utils/cn"
import SmartImage from "@/components/SmartImage"

export function Alert({
  severity = "info",
  children,
  onClose,
  className = "",
}: {
  severity?: "info" | "error" | "warning" | "success"
  children: React.ReactNode
  onClose?: () => void
  className?: string
}) {
  const palette = {
    info: "bg-(--brand-main)/(--opacity-dim) text-(--brand-main) border-(--brand-main)/(--opacity-dim)",
    error:
      "bg-(--error-text)/(--opacity-dim) text-(--error-text) border-(--error-text)/(--opacity-dim)",
    warning:
      "bg-(--warning-text)/(--opacity-dim) text-(--warning-text) border-(--warning-text)/(--opacity-dim)",
    success:
      "bg-(--success-bg)/(--opacity-dim) text-(--success-bg) border-(--success-bg)/(--opacity-dim)",
  }

  return (
    <div
      role="alert"
      className={cn(
        "flex items-center gap-3 rounded-xl border px-4 py-3 backdrop-blur-md shadow-sm",
        palette[severity],
        className
      )}
    >
      <span className="flex-1 text-sm font-semibold leading-relaxed">{children}</span>
      {onClose && (
        <button
          onClick={onClose}
          className="rounded-xs p-1 transition hover:bg-black/(--opacity-faint) dark:hover:bg-white/(--opacity-faint)"
        >
          ×
        </button>
      )}
    </div>
  )
}

export function Chip({
  label,
  color = "default",
  className = "",
  ...props
}: {
  label: string
  color?: "default" | "success" | "primary"
  className?: string
} & React.HTMLAttributes<HTMLSpanElement>) {
  const colorMap = {
    default: "text-(--text-secondary) bg-glass-bg border-glass-border",
    success:
      "text-(--success-bg) bg-(--success-bg)/(--opacity-subtle) border-(--success-bg)/(--opacity-dim)",
    primary:
      "text-(--brand-main) bg-(--brand-main)/(--opacity-subtle) border-(--brand-main)/(--opacity-dim)",
  }

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-3 py-1 text-xs font-bold tracking-tight shadow-sm backdrop-blur-md",
        colorMap[color],
        className
      )}
      {...props}
    >
      {label}
    </span>
  )
}

export function Avatar({
  src,
  alt,
  imgProps,
  className = "",
}: {
  src: string
  alt: string
  imgProps?: React.ImgHTMLAttributes<HTMLImageElement>
  className?: string
}) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-full p-1",
        "bg-linear-to-tr from-brand to-brand/(--opacity-dim) shadow-glass",
        className
      )}
    >
      <div className="relative h-full w-full overflow-hidden rounded-full bg-surface">
        <SmartImage
          srcRaw={src}
          alt={alt}
          className="h-full w-full object-cover"
          responsiveWidths={[64, 96, 128, 196]}
          sizes="(max-width: 40rem) 6rem, 9rem"
          {...imgProps}
        />
      </div>
    </div>
  )
}

export function Skeleton({
  variant = "rectangular",
  width,
  height,
  className = "",
  style,
}: {
  variant?: "circular" | "rectangular" | "rounded" | "text"
  width?: string | number
  height?: string | number
  className?: string
  style?: React.CSSProperties
}) {
  return (
    <div
      className={cn(
        "animate-pulse bg-white/(--opacity-subtle) dark:bg-white/(--opacity-dim)",
        variant === "circular"
          ? "rounded-full"
          : variant === "rounded"
            ? "rounded-xl"
            : "rounded-none",
        className
      )}
      style={{
        width: typeof width === "number" ? `${width * 0.0625}rem` : width,
        height: typeof height === "number" ? `${height * 0.0625}rem` : height,
        ...style,
      }}
    />
  )
}

export function CircularProgress({
  size = 24,
  className = "",
}: {
  size?: number
  color?: string
  className?: string
}) {
  return <Loader2 className={cn("animate-spin text-brand", className)} width={size} height={size} />
}

export function Snackbar({
  open,
  onClose,
  autoHideDuration,
  anchorOrigin,
  children,
  className = "",
}: {
  open: boolean
  onClose: () => void
  autoHideDuration?: number
  anchorOrigin?: { vertical: string; horizontal: string }
  children: React.ReactNode
  className?: string
}) {
  useEffect(() => {
    if (open && autoHideDuration) {
      const timer = setTimeout(onClose, autoHideDuration)
      return () => clearTimeout(timer)
    }
  }, [open, autoHideDuration, onClose])

  if (!open) return null

  const positionClasses =
    anchorOrigin?.vertical === "bottom"
      ? "bottom-8"
      : anchorOrigin?.vertical === "top"
        ? "top-8"
        : "top-1/2 -translate-y-1/2"
  const horizontalClasses =
    anchorOrigin?.horizontal === "center"
      ? "left-1/2 -translate-x-1/2"
      : anchorOrigin?.horizontal === "right"
        ? "right-8"
        : "left-8"

  return (
    <div
      className={cn(
        "fixed pointer-events-none z-toast",
        positionClasses,
        horizontalClasses,
        className
      )}
    >
      {children}
    </div>
  )
}
