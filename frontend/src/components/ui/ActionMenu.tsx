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
  useId,
  type ReactNode,
  type MouseEvent,
  type KeyboardEvent,
} from "react"

import { MoreVertical as MoreVertIcon } from "lucide-react"
import { useTranslation } from "react-i18next"
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

type DataAttributes = {
  [key: `data-${string}`]: string | number | boolean | undefined
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
  /** Stable identifier for the trigger button */
  triggerId?: string
  /** Stable identifier for the menu */
  menuId?: string
  /** Whether the trigger is disabled */
  disabled?: boolean
  /** Focus the first enabled item when the menu opens */
  autoFocusFirstItem?: boolean
  /** Data attributes forwarded to the trigger */
  triggerDataAttributes?: DataAttributes
  /** Data attributes forwarded to the menu */
  menuDataAttributes?: DataAttributes
}

export const ActionMenu = ({
  items,
  trigger,
  triggerClassName,
  menuClassName,
  placement = "bottom-end",
  ariaLabel,
  triggerId,
  menuId,
  disabled,
  autoFocusFirstItem,
  triggerDataAttributes,
  menuDataAttributes,
}: ActionMenuProps) => {
  const { t } = useTranslation("navigation")
  const resolvedAriaLabel = ariaLabel ?? t("navigation:aria.openMenu")
  const generatedId = useId()
  const resolvedMenuId = menuId ?? (triggerId ? `${triggerId}-menu` : `action-menu-${generatedId}`)
  const resolvedTriggerId = triggerId ?? (menuId ? `${menuId}-button` : `${resolvedMenuId}-button`)
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
        event.preventDefault()
        event.stopPropagation()
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
        event.stopPropagation()
        const nextIndex = (currentIndex + 1) % menuItems.length
        menuItems[nextIndex]?.focus()
      } else if (event.key === "ArrowUp") {
        event.preventDefault()
        event.stopPropagation()
        const prevIndex = (currentIndex - 1 + menuItems.length) % menuItems.length
        menuItems[prevIndex]?.focus()
      } else if (event.key === "Escape") {
        event.preventDefault()
        event.stopPropagation()
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

  useEffect(() => {
    if (!isOpen || !autoFocusFirstItem) return

    const firstItem = menuRef.current?.querySelector<HTMLButtonElement>("button:not(:disabled)")
    firstItem?.focus()
  }, [autoFocusFirstItem, isOpen])

  useEffect(() => {
    if (disabled && isOpen) setIsOpen(false)
  }, [disabled, isOpen])

  const placementStyles = {
    "bottom-end": "right-0",
    "bottom-start": "left-0",
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        ref={triggerRef}
        id={resolvedTriggerId}
        type="button"
        disabled={disabled}
        onClick={handleToggle}
        onKeyDown={handleKeyDown}
        aria-label={resolvedAriaLabel}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-controls={isOpen ? resolvedMenuId : undefined}
        {...triggerDataAttributes}
        className={cn(
          "flex h-11 w-11 items-center justify-center rounded-full text-(--text-secondary) transition-fast hover:bg-(--bg-surface-hover) hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-border-focus",
          triggerClassName
        )}
      >
        {trigger ?? <MoreVertIcon fontSize="small" />}
      </button>

      {isOpen && (
        <div
          ref={menuRef}
          id={resolvedMenuId}
          role="menu"
          aria-labelledby={resolvedTriggerId}
          tabIndex={-1}
          onKeyDown={handleKeyDown}
          {...menuDataAttributes}
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
                "flex min-h-11 w-full items-center gap-2 px-4 py-2.5 text-left text-sm font-medium transition-fast",
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
