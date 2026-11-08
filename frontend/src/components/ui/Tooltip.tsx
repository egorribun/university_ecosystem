import { cloneElement, useId } from "react"
import type { ReactElement, ReactNode } from "react"
import { cn } from "@/utils/cn"

type TooltipProps = {
  content: ReactNode
  children: ReactElement
  className?: string
  id?: string
  /** Keep referenced text as a description without adding it to ancestor names. */
  descriptionOnly?: boolean
}

export function Tooltip({ content, children, className, id, descriptionOnly }: TooltipProps) {
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
      <span id={tooltipId} role="tooltip" className="sr-only" hidden={descriptionOnly}>
        {content}
      </span>
    </span>
  )
}

Tooltip.displayName = "Tooltip"
