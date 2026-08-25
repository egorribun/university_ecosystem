import { useState, useRef, useEffect } from "react"
import { Link } from "@tanstack/react-router"
import { m, AnimatePresence } from "framer-motion"
import { MoreHorizontal } from "lucide-react"
import { useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"
import { springSoft } from "@/utils/animations"
import type { NavigationItem } from "@/config/navigation"

interface NavbarOverflowMenuProps {
  items: NavigationItem[]
  isActive: (to: string) => boolean
  go: (to: string) => void
  prefersReducedMotion: boolean
  isCompact: boolean
}

export function NavbarOverflowMenu({
  items,
  isActive,
  go,
  prefersReducedMotion,
}: NavbarOverflowMenuProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (open) menuRef.current?.querySelector<HTMLElement>("[role='menuitem']")?.focus()
  }, [open])

  // Close on outside click
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("pointerdown", handler)
    return () => document.removeEventListener("pointerdown", handler)
  }, [open])

  // Close on Escape
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault()
        setOpen(false)
        triggerRef.current?.focus()
      }
    }
    document.addEventListener("keydown", handler)
    return () => document.removeEventListener("keydown", handler)
  }, [open])

  if (items.length === 0) return null

  const hasActive = items.some((it) => isActive(it.to))

  return (
    <div ref={ref} className="relative">
      <m.button
        ref={triggerRef}
        type="button"
        whileTap={prefersReducedMotion ? undefined : { scale: 0.95 }}
        transition={prefersReducedMotion ? { duration: 0 } : springSoft}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-controls="navbar-overflow-menu"
        aria-label={t("navigation:aria.overflowMenu")}
        className={cn(
          "flex size-11 items-center justify-center rounded-xl transition-[transform,opacity,background-color,color]",
          prefersReducedMotion ? "duration-0" : "duration-200",
          hasActive
            ? "nav-active text-(--nav-active-color) bg-(--bg-surface-hover)"
            : "text-(--text-secondary) hover:text-(--text-primary) hover:bg-(--bg-surface-hover)/(--opacity-soft)"
        )}
      >
        <MoreHorizontal size={18} />
      </m.button>

      <AnimatePresence>
        {open && (
          <m.div
            id="navbar-overflow-menu"
            ref={menuRef}
            initial={{ opacity: 0, scale: 0.95, y: -4 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -4 }}
            transition={
              prefersReducedMotion ? { duration: 0 } : { duration: 0.15, ease: [0.16, 1, 0.3, 1] }
            }
            role="menu"
            aria-label={t("navigation:aria.overflowMenu")}
            className="absolute right-0 top-full z-dropdown mt-2 min-w-48 rounded-xl border border-(--glass-border) bg-(--pill-bg) p-1.5 shadow-md"
            onKeyDown={(event) => {
              const menuItems = Array.from(
                menuRef.current?.querySelectorAll<HTMLElement>("[role='menuitem']") ?? []
              )
              const currentIndex = menuItems.indexOf(document.activeElement as HTMLElement)
              let nextIndex: number | undefined
              if (event.key === "ArrowDown") nextIndex = (currentIndex + 1) % menuItems.length
              if (event.key === "ArrowUp")
                nextIndex = (currentIndex - 1 + menuItems.length) % menuItems.length
              if (event.key === "Home") nextIndex = 0
              if (event.key === "End") nextIndex = menuItems.length - 1
              const nextItem = nextIndex === undefined ? undefined : menuItems[nextIndex]
              if (nextItem) {
                event.preventDefault()
                nextItem.focus()
              }
            }}
          >
            {items.map((item) => {
              const Icon = item.icon
              const active = isActive(item.to)
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  role="menuitem"
                  tabIndex={-1}
                  onClick={(event) => {
                    event.preventDefault()
                    setOpen(false)
                    go(item.to)
                  }}
                  className="mobile-nav-link text-sm"
                  data-active={active || undefined}
                >
                  <Icon size={16} aria-hidden="true" />
                  {item.label}
                </Link>
              )
            })}
          </m.div>
        )}
      </AnimatePresence>
    </div>
  )
}
