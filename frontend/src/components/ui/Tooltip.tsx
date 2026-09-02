import { cloneElement, useId } from "react"
import type { ReactElement, ReactNode } from "react"
import { cn } from "@/utils/cn"

type TooltipProps = {
  content: ReactNode
  children: ReactElement
  className?: string
  id?: string
}

export function Tooltip({ content, children, className, id }: TooltipProps) {
  const generatedId = useId()
  const tooltipId = id ?? generatedId

  const label = typeof content === "string" ? content : undefined

  const clonedProps = {
    "aria-describedby": tooltipId,
    "data-tooltip": label,
  } as Partial<typeof children.props> & {
    title?: string
    "aria-describedby": string
    "data-tooltip": string | undefined
  }

  if (label) {
    clonedProps.title = label
  }

  return (
    <span className={cn("inline-flex", className)} data-tooltip-id={tooltipId}>
      {cloneElement(children, clonedProps)}
      <span id={tooltipId} role="tooltip" className="sr-only">
        {content}
      </span>
    </span>
  )
}

Tooltip.displayName = "Tooltip"
