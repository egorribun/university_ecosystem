/**
 * ActionMenu - Reusable dropdown menu for card actions
 *
 * Handles click-outside dismissal and keyboard navigation.
 *
 * @example
 * ```tsx
 * <ActionMenu
 *   items={[
 *     { label: 'Edit', icon: <EditIcon />, onClick: handleEdit },
 *     { label: 'Delete', icon: <DeleteIcon />, onClick: handleDelete, variant: 'danger' },
 *   ]}
 * />
 * ```
 */

import {
  useState,
  useRef,
  useEffect,
  useCallback,
  type ReactNode,
  type MouseEvent,
  type KeyboardEvent,
} from "react"

import { MoreVertical as MoreVertIcon } from "lucide-react"
import { cn } from "@/utils/cn"

export interface ActionMenuItem {
  /** Menu item label */
  label: string
  /** Optional icon */
  icon?: ReactNode
  /** Click handler */
  onClick: () => void
  /** Variant for styling */
  variant?: "default" | "danger"
  /** Whether item is disabled */
  disabled?: boolean
  /** Optional aria-label override */
  ariaLabel?: string
}

export interface ActionMenuProps {
  /** Menu items to display */
  items: ActionMenuItem[]
  /** Optional trigger button content */
  trigger?: ReactNode
  /** Custom class for trigger button */
  triggerClassName?: string
  /** Custom class for menu container */
  menuClassName?: string
  /** Placement of menu */
  placement?: "bottom-end" | "bottom-start"
  /** Aria label for trigger button */
  ariaLabel?: string
}

export const ActionMenu = ({
  items,
  trigger,
  triggerClassName,
  menuClassName,
  placement = "bottom-end",
  ariaLabel = "Open menu",
}: ActionMenuProps) => {
  const [isOpen, setIsOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)

  const handleToggle = useCallback((event: MouseEvent) => {
    event.stopPropagation()
    setIsOpen((prev) => !prev)
  }, [])

  const handleClose = useCallback(() => {
    setIsOpen(false)
    triggerRef.current?.focus()
  }, [])

  const handleItemClick = useCallback(
    (item: ActionMenuItem) => (event: MouseEvent) => {
      event.stopPropagation()
      item.onClick()
      handleClose()
    },
    [handleClose]
  )

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLButtonElement | HTMLDivElement>) => {
      if (event.key === "Escape") {
        handleClose()
      } else if (event.key === "ArrowDown" && isOpen) {
        event.preventDefault()
        const firstItem = menuRef.current?.querySelector<HTMLButtonElement>("button:not(:disabled)")
        firstItem?.focus()
      }
    },
    [handleClose, isOpen]
  )

  const handleItemKeyDown = useCallback(
    (event: KeyboardEvent<HTMLButtonElement>) => {
      const menuItems =
        menuRef.current!.querySelectorAll<HTMLButtonElement>("button:not(:disabled)")

      // `index` from the source items array is not safe here because disabled
      // items are excluded from `menuItems`. Navigate relative to the actual
      // enabled control that received the event instead.
      const currentIndex = Array.from(menuItems).indexOf(event.currentTarget)

      if (event.key === "ArrowDown") {
        event.preventDefault()
        const nextIndex = (currentIndex + 1) % menuItems.length
        menuItems[nextIndex]?.focus()
      } else if (event.key === "ArrowUp") {
        event.preventDefault()
        const prevIndex = (currentIndex - 1 + menuItems.length) % menuItems.length
        menuItems[prevIndex]?.focus()
      } else if (event.key === "Escape") {
        handleClose()
      }
    },
    [handleClose]
  )

  // Click outside handler
  useEffect(() => {
    if (!isOpen) return

    const handleClickOutside = (event: globalThis.MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        handleClose()
      }
    }

    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [isOpen, handleClose])

  const placementStyles = {
    "bottom-end": "right-0",
    "bottom-start": "left-0",
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        ref={triggerRef}
        type="button"
        onClick={handleToggle}
        onKeyDown={handleKeyDown}
        aria-label={ariaLabel}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        className={cn(
          "flex h-8 w-8 items-center justify-center rounded-full text-(--text-secondary) transition-fast hover:bg-(--bg-surface-hover) hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-border-focus",
          triggerClassName
        )}
      >
        {trigger ?? <MoreVertIcon fontSize="small" />}
      </button>

      {isOpen && (
        <div
          ref={menuRef}
          role="menu"
          tabIndex={-1}
          onKeyDown={handleKeyDown}
          className={cn(
            "absolute top-full z-overlay mt-1 w-40 overflow-hidden rounded-lg border border-glass-border-subtle bg-glass-elevated shadow-lg backdrop-blur-md",
            placementStyles[placement],
            menuClassName
          )}
        >
          {items.map((item) => (
            <button
              key={item.label}
              type="button"
              role="menuitem"
              disabled={item.disabled}
              onClick={handleItemClick(item)}
              onKeyDown={handleItemKeyDown}
              aria-label={item.ariaLabel}
              className={cn(
                "flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm font-medium transition-fast",
                "hover:bg-(--bg-surface-hover) focus-visible:bg-(--bg-surface-hover) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-border-focus",
                item.variant === "danger"
                  ? "text-error-text hover:bg-error-bg"
                  : "text-text-primary",
                item.disabled && "cursor-not-allowed opacity-medium"
              )}
            >
              {item.icon && (
                <span className="shrink-0 text-(--text-secondary) transition-transform duration-fast group-hover:scale-110">
                  {item.icon}
                </span>
              )}
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

ActionMenu.displayName = "ActionMenu"
