import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type KeyboardEvent as ReactKeyboardEvent,
  type MutableRefObject,
  type PropsWithChildren,
} from "react"
import { createPortal } from "react-dom"
import { cn } from "@/utils/cn"

type PositionStyle = { top: number; left: number; transformOrigin: string }

type DropdownContextValue = {
  open: boolean
  onOpenChange: (open: boolean) => void
  triggerRef: MutableRefObject<HTMLElement | null>
  contentRef: MutableRefObject<HTMLDivElement | null>
  menuId: string
}

const DropdownMenuContext = createContext<DropdownContextValue | null>(null)

const isBrowser = typeof document !== "undefined"

const getPortalRoot = () => {
  if (!isBrowser) return null
  const existing = document.getElementById("ue-dropdown-root")
  if (existing) return existing
  const node = document.createElement("div")
  node.setAttribute("id", "ue-dropdown-root")
  document.body.appendChild(node)
  return node
}

export interface DropdownMenuProps extends PropsWithChildren {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function DropdownMenu({ open, onOpenChange, children }: DropdownMenuProps) {
  const triggerRef = useRef<HTMLElement | null>(null)
  const contentRef = useRef<HTMLDivElement | null>(null)
  const menuId = useId()

  const value = useMemo(
    () => ({ open, onOpenChange, triggerRef, contentRef, menuId }),
    [open, onOpenChange, menuId]
  )

  return <DropdownMenuContext.Provider value={value}>{children}</DropdownMenuContext.Provider>
}

const useDropdownContext = () => {
  const context = useContext(DropdownMenuContext)
  if (!context) {
    throw new Error("DropdownMenu components must be used within <DropdownMenu>")
  }
  return context
}

export type DropdownMenuTriggerProps = ButtonHTMLAttributes<HTMLButtonElement>

export function DropdownMenuTrigger({
  onClick,
  onKeyDown,
  children,
  className,
  type = "button",
  ...rest
}: DropdownMenuTriggerProps) {
  const { open, onOpenChange, triggerRef, menuId } = useDropdownContext()
  const triggerId = useId()

  const handleToggle = useCallback(
    (next: boolean) => {
      onOpenChange(next)
      if (!next && triggerRef.current) {
        triggerRef.current.focus()
      }
    },
    [onOpenChange, triggerRef]
  )

  const handleClick = useCallback<NonNullable<typeof onClick>>(
    (event) => {
      onClick?.(event)
      if (event.defaultPrevented) return
      handleToggle(!open)
    },
    [onClick, handleToggle, open]
  )

  const handleKeyDown = useCallback<NonNullable<typeof onKeyDown>>(
    (event) => {
      onKeyDown?.(event)
      if (event.defaultPrevented) return
      if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
        event.preventDefault()
        handleToggle(true)
      }
      if (event.key === "ArrowUp") {
        event.preventDefault()
        handleToggle(true)
      }
      if (event.key === "Escape") {
        event.preventDefault()
        handleToggle(false)
      }
    },
    [onKeyDown, handleToggle]
  )

  return (
    <button
      id={triggerId}
      ref={(node) => {
        triggerRef.current = node
      }}
      type={type}
      className={cn(
        "inline-flex items-center gap-2 rounded-full border border-[color:var(--glass-border)] bg-[color:var(--card-bg)] px-3 py-2 text-sm font-semibold text-[color:var(--nav-link)] shadow-surface transition-all",
        "hover:bg-[color:var(--menu-hover-bg)] hover:text-[color:var(--menu-hover-text)]",
        "focus-visible:outline-none focus-visible:shadow-[var(--ue-focus-ring)]",
        className
      )}
      aria-haspopup="menu"
      aria-expanded={open ? "true" : "false"}
      aria-controls={menuId}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      {...rest}
    >
      {children}
    </button>
  )
}

export interface DropdownMenuContentProps extends HTMLAttributes<HTMLDivElement> {
  align?: "start" | "end"
  portalContainer?: HTMLElement | null
  autoFocus?: boolean
}

const focusFirstItem = (container: HTMLElement | null) => {
  if (!container) return
  const items = getFocusableItems(container)
  items[0]?.focus()
}

const getFocusableItems = (container: HTMLElement | null) => {
  if (!container) return []
  return Array.from(
    container.querySelectorAll<HTMLElement>('[data-ue-dropdown-item]:not([data-disabled="true"])')
  )
}

const focusNextItem = (container: HTMLElement | null, direction: 1 | -1) => {
  if (!container) return
  const items = getFocusableItems(container)
  if (items.length === 0) return
  const active = document.activeElement as HTMLElement | null
  const currentIndex = active ? items.indexOf(active) : -1
  const nextIndex = (currentIndex + direction + items.length) % items.length
  items[nextIndex]?.focus()
}

const computePosition = (
  trigger: HTMLElement,
  content: HTMLElement,
  align: "start" | "end"
): PositionStyle => {
  const rect = trigger.getBoundingClientRect()
  const contentRect = content.getBoundingClientRect()
  const margin = 12
  let top = rect.bottom + 8
  let left = align === "end" ? rect.right - contentRect.width : rect.left
  let origin = "top"

  const viewportHeight = window.innerHeight
  if (top + contentRect.height > viewportHeight - margin) {
    top = Math.max(rect.top - contentRect.height - 8, margin)
    origin = "bottom"
  }

  const viewportWidth = window.innerWidth
  if (left + contentRect.width > viewportWidth - margin) {
    left = viewportWidth - margin - contentRect.width
  }
  if (left < margin) {
    left = margin
  }

  return {
    top,
    left,
    transformOrigin: `${origin} ${align === "end" ? "right" : "left"}`,
  }
}

export function DropdownMenuContent({
  className,
  children,
  align = "start",
  portalContainer,
  autoFocus = true,
  ...rest
}: DropdownMenuContentProps) {
  const { open, onOpenChange, triggerRef, contentRef, menuId } = useDropdownContext()
  const [position, setPosition] = useState<PositionStyle | null>(null)
  const portalNode = useMemo(() => portalContainer ?? getPortalRoot(), [portalContainer])

  useLayoutEffect(() => {
    if (!open) return
    const trigger = triggerRef.current
    const content = contentRef.current
    if (!trigger || !content) return

    const update = () => {
      if (!triggerRef.current || !contentRef.current) return
      const coords = computePosition(triggerRef.current, contentRef.current, align)
      setPosition(coords)
    }

    update()

    const handleScroll = () => update()
    const handleResize = () => update()

    window.addEventListener("scroll", handleScroll, true)
    window.addEventListener("resize", handleResize)

    let resizeObserver: ResizeObserver | null = null
    if (typeof ResizeObserver !== "undefined") {
      resizeObserver = new ResizeObserver(update)
      resizeObserver.observe(content)
    }

    return () => {
      window.removeEventListener("scroll", handleScroll, true)
      window.removeEventListener("resize", handleResize)
      resizeObserver?.disconnect()
    }
  }, [open, triggerRef, contentRef, align])

  useEffect(() => {
    if (!open) return undefined
    const content = contentRef.current
    if (autoFocus) {
      requestAnimationFrame(() => {
        focusFirstItem(content)
      })
    }

    const handlePointerDown = (event: PointerEvent) => {
      if (!content || !triggerRef.current) return
      if (
        !content.contains(event.target as Node) &&
        !triggerRef.current.contains(event.target as Node)
      ) {
        onOpenChange(false)
      }
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault()
        onOpenChange(false)
        triggerRef.current?.focus()
      }
    }

    document.addEventListener("pointerdown", handlePointerDown)
    window.addEventListener("keydown", handleKeyDown)

    return () => {
      document.removeEventListener("pointerdown", handlePointerDown)
      window.removeEventListener("keydown", handleKeyDown)
    }
  }, [open, autoFocus, onOpenChange, triggerRef])

  const handleKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLDivElement>) => {
      if (event.key === "ArrowDown") {
        event.preventDefault()
        focusNextItem(contentRef.current, 1)
      }
      if (event.key === "ArrowUp") {
        event.preventDefault()
        focusNextItem(contentRef.current, -1)
      }
      if (event.key === "Home") {
        event.preventDefault()
        focusFirstItem(contentRef.current)
      }
      if (event.key === "End") {
        event.preventDefault()
        const items = getFocusableItems(contentRef.current)
        items[items.length - 1]?.focus()
      }
      if (event.key === "Tab") {
        event.preventDefault()
        onOpenChange(false)
        triggerRef.current?.focus()
      }
    },
    [contentRef, onOpenChange, triggerRef]
  )

  if (!open || !portalNode) return null

  return createPortal(
    <div
      ref={(node) => {
        contentRef.current = node
      }}
      id={menuId}
      role="menu"
      aria-labelledby={triggerRef.current?.id}
      className={cn(
        "fixed min-w-[12rem] overflow-hidden rounded-[var(--ue-radius-md,0.75rem)] border border-[color:var(--glass-border)] bg-[color:var(--card-bg)]/98",
        "shadow-[0_24px_64px_rgba(15,23,42,0.32)] backdrop-blur-xl",
        "focus-visible:outline-none",
        "transition-[opacity,transform] duration-150 ease-out",
        className
      )}
      style={{
        top: position?.top ?? -9999,
        left: position?.left ?? -9999,
        transformOrigin: position?.transformOrigin,
        zIndex: "var(--ue-z-index-floating)",
        opacity: position ? 1 : 0,
      }}
      onKeyDown={handleKeyDown}
      tabIndex={-1}
      {...rest}
    >
      <div className="flex flex-col py-2">{children}</div>
    </div>,
    portalNode
  )
}

export interface DropdownMenuItemProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  inset?: boolean
}

export function DropdownMenuItem({
  inset = false,
  className,
  disabled,
  onClick,
  children,
  ...rest
}: DropdownMenuItemProps) {
  const { onOpenChange } = useDropdownContext()

  const handleClick = useCallback<NonNullable<typeof onClick>>(
    (event) => {
      onClick?.(event)
      if (event.defaultPrevented) return
      if (disabled) return
      onOpenChange(false)
    },
    [onClick, onOpenChange, disabled]
  )

  return (
    <button
      type="button"
      className={cn(
        "flex w-full items-center gap-3 px-4 py-2 text-left text-sm font-medium transition-colors",
        "text-[color:var(--nav-text)] hover:bg-[color:var(--menu-hover-bg)] hover:text-[color:var(--menu-hover-text)]",
        "focus-visible:outline-none focus-visible:bg-[color:var(--menu-hover-bg)] focus-visible:text-[color:var(--menu-hover-text)]",
        disabled && "cursor-not-allowed opacity-60",
        inset && "pl-9",
        className
      )}
      role="menuitem"
      tabIndex={-1}
      data-ue-dropdown-item
      data-disabled={disabled ? "true" : undefined}
      aria-disabled={disabled ? "true" : undefined}
      disabled={disabled}
      onClick={handleClick}
      {...rest}
    >
      {children}
    </button>
  )
}

DropdownMenu.displayName = "DropdownMenu"
DropdownMenuTrigger.displayName = "DropdownMenuTrigger"
DropdownMenuContent.displayName = "DropdownMenuContent"
DropdownMenuItem.displayName = "DropdownMenuItem"
