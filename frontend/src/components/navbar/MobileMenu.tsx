import { createPortal } from "react-dom"
import { useEffect } from "react"
import { Link } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { Settings } from "lucide-react"
import { cn } from "@/utils/cn"
import { useAppShell } from "@/contexts/AppShellContext"
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

  return createPortal(
    <>
      <button
        type="button"
        className={cn(
          "mobile-drawer-backdrop fixed inset-0 z-overlay h-full w-full border-none p-0 cursor-default outline-none",
          isOpen
            ? "pointer-events-auto bg-black/(--opacity-dim)"
            : "pointer-events-none bg-transparent",
          !prefersReducedMotion && "transition-colors duration-fast"
        )}
        onClick={onClose}
        aria-label={t("navigation:aria.closeMenu")}
        data-testid="mobile-menu-backdrop"
        tabIndex={-1}
      />

      <div
        id="mobile-drawer"
        role="dialog"
        aria-modal="true"
        aria-label={t("navigation:aria.mobileMenu")}
        ref={drawerTrapRef}
        className={cn(
          "fixed inset-y-0 left-0 z-overlay flex h-full w-(--mobile-menu-w) max-w-(--w-drawer-mobile-max) flex-col bg-(--glass-bg) shadow-2xl transition-transform duration-slow ease-premium",
          "border-r border-(--glass-border) backdrop-blur-(--glass-blur)",
          isOpen ? "translate-x-0" : "-translate-x-full"
        )}
        tabIndex={-1}
      >
        <div className="flex-1 overflow-y-auto px-4 py-8">
          <ul className="flex flex-col gap-2">
            {menuLinks.map((item) => {
              const Icon = item.icon
              const active = isActive(item.to)
              return (
                <li key={item.to}>
                  <Link
                    id={`mobile-nav-link-${item.to.replace(/\//g, "") || "home"}`}
                    to={item.to}
                    onClick={onClose}
                    className={cn(
                      "flex items-center gap-4 rounded-2xl px-5 py-4 text-base font-semibold transition-all duration-base",
                      active
                        ? "bg-(--primary-main)/(--opacity-subtle) text-(--primary-main) shadow-sm"
                        : "text-(--nav-text) hover:bg-(--glass-tint-1) hover:translate-x-1"
                    )}
                  >
                    {Icon && (
                      <Icon
                        className={cn(
                          "text-icon-lg transition-colors",
                          active ? "text-(--primary-main)" : "text-(--text-secondary)"
                        )}
                      />
                    )}
                    {item.label}
                  </Link>
                </li>
              )
            })}
            {isAuth && user && (
              <li className="mt-4 pt-4 border-t border-(--glass-border)">
                <button
                  id="mobile-nav-link-settings"
                  type="button"
                  className={cn(
                    "flex w-full items-center gap-4 rounded-2xl px-5 py-4 text-base font-semibold transition-all duration-base",
                    isActive("/settings")
                      ? "bg-(--primary-main)/(--opacity-subtle) text-(--primary-main) shadow-sm"
                      : "text-(--nav-text) hover:bg-(--glass-tint-1) hover:translate-x-1"
                  )}
                  onClick={(e) => {
                    e.stopPropagation()
                    onClose()
                    go("/settings")
                  }}
                  aria-label={t("navigation:menu.settings")}
                >
                  <Settings
                    className={cn(
                      "text-icon-lg transition-colors",
                      isActive("/settings") ? "text-(--primary-main)" : "text-(--text-secondary)"
                    )}
                  />
                  {t("navigation:menu.settings")}
                </button>
              </li>
            )}
          </ul>
        </div>

        <div className="border-t border-(--glass-border) p-8">
          <div className="text-center text-xs font-medium text-(--text-secondary) opacity-medium">
            © {new Date().getFullYear()} {t("navigation:brandName")}
          </div>
        </div>
      </div>
    </>,
    document.body
  )
}
