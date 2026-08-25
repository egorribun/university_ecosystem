import { createPortal } from "react-dom"
import { useEffect, useCallback } from "react"
import { Link } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { X } from "lucide-react"
import { m } from "framer-motion"
import { cn } from "@/utils/cn"
import { useAppShell } from "@/contexts/AppShellContext"
import { useSwipeGesture } from "@/hooks/useSwipeGesture"
import { MobileDrawerProfile } from "./MobileDrawerProfile"
import { MobileDrawerQuickActions } from "./MobileDrawerQuickActions"
import { springSoft } from "@/utils/animations"
import type { User } from "@/types/User"

interface MenuLink {
  to: string
  label: string
  icon?: React.ElementType
}

interface MobileMenuProps {
  isOpen: boolean
  onClose: () => void
  menuLinks: MenuLink[]
  isActive: (to: string) => boolean
  go: (to: string) => void
  user: User | null
  isAuth: boolean
  prefersReducedMotion: boolean
  drawerTrapRef: React.RefObject<HTMLDivElement | null>
}

const drawerSpring = {
  type: "spring" as const,
  stiffness: 300,
  damping: 28,
  mass: 0.8,
}

export function MobileMenu({
  isOpen,
  onClose,
  menuLinks,
  isActive,
  go,
  user,
  isAuth,
  prefersReducedMotion,
  drawerTrapRef,
}: MobileMenuProps) {
  const { t } = useTranslation(["navigation"])
  const { setOverlayState } = useAppShell()

  const handleClose = useCallback(() => onClose(), [onClose])

  const { dragOffset, handlers } = useSwipeGesture({
    direction: "right",
    threshold: 80,
    onSwipeClose: handleClose,
    enabled: isOpen,
  })

  // Prevent scrolling and manage overlay blur
  useEffect(() => {
    if (isOpen) {
      setOverlayState("mobile-drawer", {
        scrollLocked: true,
        blurred: !prefersReducedMotion,
      })
    } else {
      setOverlayState("mobile-drawer", null)
    }
    return () => {
      setOverlayState("mobile-drawer", null)
    }
  }, [isOpen, prefersReducedMotion, setOverlayState])

  // Handle Escape key globally
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen && !e.defaultPrevented) {
        onClose()
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [isOpen, onClose])

  const handleSearch = () => {
    onClose()
    // Trigger Cmd+K search dialog
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true, bubbles: true }))
  }

  if (!isOpen) return null

  return createPortal(
    <>
      {/* Backdrop */}
      <m.button
        type="button"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={prefersReducedMotion ? { duration: 0 } : { duration: 0.2 }}
        className="fixed inset-0 z-overlay h-full w-full border-none p-0 cursor-default outline-none bg-(--drawer-overlay) backdrop-blur-sm"
        onClick={onClose}
        aria-label={t("navigation:aria.closeMenu")}
        data-testid="mobile-menu-backdrop"
        tabIndex={-1}
      />

      {/* Drawer — slides from RIGHT */}
      <m.div
        id="mobile-drawer"
        role="dialog"
        aria-modal="true"
        aria-label={t("navigation:aria.mobileMenu")}
        aria-describedby="mobile-drawer-description"
        ref={drawerTrapRef}
        initial={{ x: "100%" }}
        animate={{ x: dragOffset > 0 ? dragOffset : 0 }}
        transition={prefersReducedMotion ? { duration: 0 } : drawerSpring}
        className={cn(
          "fixed inset-y-0 right-0 z-overlay flex h-dvh max-h-dvh flex-col",
          "w-(--drawer-w) max-w-(--drawer-w-max)",
          "pt-[env(safe-area-inset-top,0px)] pr-[env(safe-area-inset-right,0px)] pb-[env(safe-area-inset-bottom,0px)]",
          "drawer-glass glass-noise",
          "shadow-glass-strong"
        )}
        tabIndex={-1}
        {...handlers}
      >
        <p id="mobile-drawer-description" className="sr-only">
          {t("navigation:aria.mobileMenuDescription")}
        </p>
        {/* Decorative accent gradient line */}
        <div
          className="h-0.5 w-full shrink-0"
          style={{ background: "var(--drawer-accent-gradient)" }}
          aria-hidden="true"
        />

        {/* Close button */}
        <div className="flex items-center justify-end px-4 pt-3 pb-1">
          <m.button
            type="button"
            whileTap={prefersReducedMotion ? undefined : { scale: 0.9 }}
            transition={prefersReducedMotion ? { duration: 0 } : springSoft}
            onClick={onClose}
            className="flex size-11 items-center justify-center rounded-xl border-none bg-transparent text-(--text-secondary) transition-[transform,opacity,background-color,color] duration-200 hover:bg-(--bg-surface-hover)/(--opacity-soft) hover:text-(--text-primary) cursor-pointer"
            aria-label={t("navigation:aria.closeMenu")}
          >
            <X size={20} />
          </m.button>
        </div>

        {/* Profile card */}
        {isAuth && user && (
          <div className="px-2 pb-2">
            <MobileDrawerProfile
              user={user}
              onProfileClick={() => {
                onClose()
                go("/profile")
              }}
              t={t}
            />
          </div>
        )}

        {/* Quick actions */}
        <MobileDrawerQuickActions
          onSearch={handleSearch}
          onNotifications={() => {
            onClose()
            document.getElementById("global-notifications-btn")?.click()
          }}
          onSettings={() => {
            onClose()
            go("/settings")
          }}
          prefersReducedMotion={prefersReducedMotion}
          t={t}
        />

        {/* Separator — gradient fade */}
        <div
          className="mx-4 my-2 h-px"
          style={{
            background: "linear-gradient(90deg, transparent, var(--glass-border), transparent)",
          }}
        />

        {/* Navigation items */}
        <div className="flex-1 overflow-y-auto px-3 py-2">
          <ul
            className="flex flex-col gap-1"
            role="navigation"
            aria-label={t("navigation:aria.mobileMenu")}
          >
            {menuLinks.map((item, index) => {
              const Icon = item.icon
              const active = isActive(item.to)
              return (
                <m.li
                  key={item.to}
                  initial={prefersReducedMotion ? false : { opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={
                    prefersReducedMotion
                      ? { duration: 0 }
                      : { delay: 0.05 + index * 0.03, ...springSoft }
                  }
                >
                  <Link
                    id={`mobile-nav-link-${item.to.replace(/\//g, "") || "home"}`}
                    to={item.to}
                    onClick={onClose}
                    className="mobile-nav-link"
                    data-active={active || undefined}
                  >
                    {Icon && <Icon className="mobile-nav-link-icon shrink-0" size={18} />}
                    {item.label}
                  </Link>
                </m.li>
              )
            })}
          </ul>
        </div>

        {/* Footer */}
        <div className="border-t border-(--glass-border) px-6 py-4">
          <div className="text-center text-xs font-medium text-(--text-tertiary)">
            © {new Date().getFullYear()} {t("navigation:brandName")}
          </div>
        </div>
      </m.div>
    </>,
    document.body
  )
}
