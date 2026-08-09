import React, { useId, useRef, useState } from "react"
import { m } from "framer-motion"
import { cn } from "@/utils/cn"

// Section Components
export function SectionCard({
  children,
  className = "",
  component = "div",
  ...props
}: {
  children: React.ReactNode
  className?: string
  component?: React.ElementType
} & React.HTMLAttributes<HTMLElement>) {
  const Component = component
  return (
    <Component
      className={cn(
        "relative flex flex-col gap-3 overflow-hidden rounded-2xl px-6 py-6",
        "border-glass-border bg-glass-bg shadow-glass backdrop-blur-glass text-text-primary",
        "transition-all duration-slow",
        "transition-all duration-slow",
        "before:pointer-events-none before:absolute before:inset-0 before-rounded-inherit before:opacity-soft",
        "before:bg-radial-gradient-primary",
        "dark:before:bg-radial-gradient-primary-dark",
        className
      )}
      {...props}
    >
      {children}
    </Component>
  )
}

export function SectionTitle({
  children,
  className = "",
  component = "h2",
  variant = "subtitle1",
  ...props
}: {
  children: React.ReactNode
  className?: string
  component?: React.ElementType
  variant?: string
} & React.HTMLAttributes<HTMLElement>) {
  const Component = component
  const sizeClasses =
    variant === "subtitle1"
      ? "text-base"
      : variant === "subtitle2"
        ? "text-sm"
        : variant === "h6"
          ? "text-lg"
          : "text-base"
  return (
    <Component
      className={cn("font-bold tracking-tight text-text-primary", sizeClasses, className)}
      {...props}
    >
      {children}
    </Component>
  )
}

export function SectionSubtitle({
  children,
  className = "",
  variant = "body2",
  ...props
}: {
  children: React.ReactNode
  className?: string
  variant?: string
} & React.HTMLAttributes<HTMLParagraphElement>) {
  const sizeClasses =
    variant === "body2" ? "text-sm" : variant === "caption" ? "text-xs" : "text-sm"
  return (
    <p className={cn("text-(--text-secondary) leading-relaxed", sizeClasses, className)} {...props}>
      {children}
    </p>
  )
}

export function SessionItem({
  children,
  className = "",
  revoked = false,
  ...props
}: {
  children: React.ReactNode
  className?: string
  revoked?: boolean
} & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "group relative flex items-stretch justify-between gap-4 rounded-xl px-4 py-3",
        "border-glass-border bg-glass-bg text-text-primary",
        "transition-all duration-slow ease-out backdrop-blur-glass",
        "hover:-translate-y-[0.125rem] hover:border-(--brand-main)/(--opacity-soft) hover:bg-glass-tint1 hover:shadow-glass",
        "max-sm:flex-col max-sm:items-start",
        className
      )}
      style={revoked ? { transform: "translateY(0)" } : undefined}
      data-revoked={revoked}
      {...props}
    >
      {children}
    </div>
  )
}

export function AccordionSection({
  title,
  subtitle,
  children,
  defaultExpanded = false,
  className = "",
}: {
  title: string
  subtitle?: string
  children: React.ReactNode
  defaultExpanded?: boolean
  className?: string
}) {
  const [expanded, setExpanded] = useState(defaultExpanded)
  const contentId = useId()

  return (
    <div
      className={cn(
        "overflow-hidden rounded-xl border transition-all duration-slow",
        "border-glass-border bg-glass-bg backdrop-blur-glass",
        expanded
          ? "shadow-glass border-(--brand-main)/(--opacity-dim) bg-glass-tint1"
          : "shadow-sm border-transparent",
        className
      )}
    >
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        aria-controls={contentId}
        className="w-full px-4 py-3 text-left transition-colors hover:bg-(--primary-main)/5"
      >
        <div className="flex items-center justify-between gap-3">
          <div className="flex flex-col gap-1 min-w-0">
            <h3 className="text-sm font-bold text-text-primary">{title}</h3>
            {subtitle && <p className="text-xs text-(--text-secondary)">{subtitle}</p>}
          </div>
          <m.svg
            animate={{ rotate: expanded ? 180 : 0 }}
            className="h-5 w-5 shrink-0 text-brand transition-transform duration-base"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </m.svg>
        </div>
      </button>
      <div
        id={contentId}
        hidden={!expanded}
        className={cn(
          "overflow-hidden transition-all duration-slow",
          expanded ? "max-h-[125rem] opacity-100" : "max-h-0 opacity-0"
        )}
        style={{ maxHeight: expanded ? "2000px" : "0px" }}
      >
        <div className="px-4 pb-4 pt-2">{children}</div>
      </div>
    </div>
  )
}

export function Divider({
  className = "",
  flexItem,
}: {
  className?: string
  flexItem?: boolean
  component?: React.ElementType
}) {
  return (
    <hr
      className={cn(
        "h-px w-full border-0 bg-glass-border",
        flexItem ? "self-stretch" : "",
        className
      )}
      style={{ opacity: "var(--opacity-medium)" }}
    />
  )
}

// Navigation Components
// Wave 175 SW6 — full ARIA APG tabs pattern:
// - role="tablist" with aria-orientation="horizontal"
// - role="tab" + aria-selected + aria-controls (each tab points at the
//   panel) + roving tabindex (active=0, inactive=-1) so Tab key skips
//   inactive tabs to reach panel content (per ARIA APG guidance).
// - Arrow-key keyboard nav (Left/Right with modulo, Home, End) — caller
//   passes `panelId` so we can stable-id tabs `${panelId}-tab-${index}`
//   and the parent wraps content in <section id={panelId} role="tabpanel"
//   aria-labelledby={${panelId}-tab-${activeIndex}}>.
// - When `panelId` not supplied, fall back to a useId()-generated value
//   so the keyboard nav + roving tabindex still work for legacy callers
//   (just without aria-controls/labelledby — the dialog still has
//   role="tab" so screen readers identify tab context).
export function Tabs({
  value,
  onChange,
  children,
  className = "",
  panelId,
  ariaLabel,
}: {
  value: number
  onChange: (e: unknown, value: number) => void
  variant?: string
  scrollButtons?: string
  children: React.ReactNode
  className?: string
  panelId?: string
  ariaLabel?: string
}) {
  const generatedId = useId()
  const resolvedPanelId = panelId ?? `${generatedId}-tabpanel`
  const tabIdPrefix = `${resolvedPanelId}-tab`
  const containerRef = useRef<HTMLDivElement | null>(null)

  const tabCount = React.Children.count(children)

  const focusTab = (index: number) => {
    const container = containerRef.current
    if (!container) return
    const tabButton = container.querySelector<HTMLButtonElement>(
      `#${CSS.escape(tabIdPrefix)}-${index}`
    )
    tabButton?.focus()
  }

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (tabCount <= 1) return
    let nextIndex: number | null = null
    switch (event.key) {
      case "ArrowRight":
        nextIndex = (value + 1) % tabCount
        break
      case "ArrowLeft":
        nextIndex = (value - 1 + tabCount) % tabCount
        break
      case "Home":
        nextIndex = 0
        break
      case "End":
        nextIndex = tabCount - 1
        break
      default:
        return
    }
    event.preventDefault()
    onChange(null, nextIndex)
    // Defer focus to next tick so the cloned button has updated tabIndex
    // (selected tab gets tabIndex=0; others get -1). Without this defer
    // browser may briefly focus the OLD tab before React re-renders.
    queueMicrotask(() => focusTab(nextIndex as number))
  }

  return (
    // ARIA APG tabs pattern: role="tablist" is a CONTAINER role; the
    // tablist itself should NOT be in tab order (only the active tab via
    // roving tabindex). ESLint jsx-a11y treats tablist as interactive
    // requiring tabIndex, but ARIA spec disagrees — disabling per W175 SW6.
    // eslint-disable-next-line jsx-a11y/interactive-supports-focus
    <div
      ref={containerRef}
      role="tablist"
      aria-orientation="horizontal"
      aria-label={ariaLabel}
      onKeyDown={handleKeyDown}
      className={cn(
        "relative flex flex-wrap items-center gap-1.5 overflow-x-auto rounded-2xl px-1.5 py-1.5",
        "border border-(--glass-border) bg-(--bg-surface)/(--opacity-soft) backdrop-blur-md shadow-glass",
        className
      )}
    >
      {React.Children.map(children, (child, index) => {
        if (React.isValidElement(child)) {
          return React.cloneElement(
            child as React.ReactElement<{
              selected?: boolean
              onClick?: () => void
              index?: number
              tabId?: string
              panelId?: string
            }>,
            {
              selected: value === index,
              index: index,
              onClick: () => onChange(null, index),
              tabId: `${tabIdPrefix}-${index}`,
              panelId: resolvedPanelId,
            }
          )
        }
        return child
      })}
    </div>
  )
}

export function Tab({
  label,
  selected,
  onClick,
  layoutId = "settings-tab-indicator",
  tabId,
  panelId,
}: {
  label: string
  selected?: boolean
  onClick?: () => void
  layoutId?: string
  // Wave 175 SW6 — supplied by parent Tabs via cloneElement.
  index?: number
  tabId?: string
  panelId?: string
}) {
  return (
    <button
      type="button"
      role="tab"
      id={tabId}
      aria-selected={selected}
      aria-controls={panelId}
      // Roving tabindex per ARIA APG — only selected tab is in Tab-key
      // order; inactive tabs are reachable via Arrow keys inside the
      // tablist. Default `selected` to false for the first-render case
      // when Tabs hasn't cloned yet.
      tabIndex={selected ? 0 : -1}
      onClick={onClick}
      className={cn(
        "relative flex h-10 items-center justify-center rounded-xl px-5 text-sm font-black transition-all duration-slow",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-(--bg-surface)",
        selected
          ? "text-text-primary"
          : "text-(--text-secondary) opacity-strong hover:opacity-100 hover:bg-(--bg-surface-hover)/(--opacity-dim)"
      )}
    >
      {selected && (
        <m.div
          layoutId={layoutId}
          className="absolute inset-0 z-hide rounded-xl bg-brand/(--opacity-subtle) ring-1 ring-brand/(--opacity-dim)"
          transition={{ type: "spring", bounce: 0.2, duration: 0.6 }}
        />
      )}
      <span className="relative z-deep">{label}</span>
    </button>
  )
}
