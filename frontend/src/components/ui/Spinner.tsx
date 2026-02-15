import { cn } from "@/utils/cn"

interface SpinnerProps {
  className?: string
  size?: "sm" | "md" | "lg"
}

const sizeClasses = {
  sm: "h-4 w-4 border-2",
  md: "h-5 w-5 border-2",
  lg: "h-8 w-8 border-3",
}

export const Spinner = ({ className, size = "md" }: SpinnerProps) => {
  return (
    <span
      className={cn(
        "inline-block animate-spin rounded-full border-current opacity-strong border-t-transparent",
        sizeClasses[size],
        className
      )}
      aria-hidden="true"
    />
  )
}
