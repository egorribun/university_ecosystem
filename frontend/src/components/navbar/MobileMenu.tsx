import { createPortal } from "react-dom"
import { useEffect } from "react"
import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import SettingsIcon from "@mui/icons-material/Settings"
import { cn } from "@/utils/cn"
import { useAppShell } from "@/contexts/AppShellContext"

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
  user: any
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

  return createPortal(
    <div
      id="mobile-drawer"
      className={cn(
        "mobile-drawer fixed inset-0 z-[var(--ue-z-index-overlay)] flex h-screen w-screen",
        isOpen ? "pointer-events-auto bg-black/40" : "pointer-events-none bg-transparent", // Darker overlay
        !prefersReducedMotion && "transition-[background] duration-200"
      )}
      style={{
        pointerEvents: isOpen ? "auto" : "none",
      }}
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={t("navigation:aria.mobileMenu")}
    >
      <nav
        ref={drawerTrapRef}
        className={cn(
          "fixed inset-y-0 left-0 z-[60] flex h-full w-[300px] max-w-[85%] flex-col bg-[var(--glass-bg)] shadow-2xl transition-transform duration-500 ease-[cubic-bezier(0.16,1,0.3,1)]",
          "border-r border-[var(--glass-border)] backdrop-blur-[var(--glass-blur)]",
          isOpen ? "translate-x-0" : "-translate-x-full"
        )}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex-1 overflow-y-auto px-4 py-8">
          <ul className="flex flex-col gap-2">
            {menuLinks.map((item) => {
              const Icon = item.icon
              const active = isActive(item.to)
              return (
                <li key={item.to}>
                  <Link
                    to={item.to}
                    onClick={onClose}
                    className={cn(
                      "flex items-center gap-4 rounded-2xl px-5 py-4 text-[16px] font-semibold transition-all duration-300",
                      active
                        ? "bg-[var(--nav-link-active-bg)] text-[var(--nav-link)] shadow-sm"
                        : "text-[var(--nav-text)] hover:bg-[var(--glass-tint-1)] hover:translate-x-1"
                    )}
                  >
                    {Icon && (
                      <Icon
                        className={cn(
                          "text-[22px] transition-colors",
                          active ? "text-[var(--nav-link)]" : "text-[var(--secondary-text)]"
                        )}
                      />
                    )}
                    {item.label}
                  </Link>
                </li>
              )
            })}
            {isAuth && user && (
              <li className="mt-4 pt-4 border-t border-[var(--glass-border)]">
                <button
                  type="button"
                  className={cn(
                    "flex w-full items-center gap-4 rounded-2xl px-5 py-4 text-[16px] font-semibold transition-all duration-300",
                    isActive("/settings")
                      ? "bg-[var(--nav-link-active-bg)] text-[var(--nav-link)] shadow-sm"
                      : "text-[var(--nav-text)] hover:bg-[var(--glass-tint-1)] hover:translate-x-1"
                  )}
                  onClick={(e) => {
                    e.stopPropagation()
                    onClose()
                    go("/settings")
                  }}
                  aria-label={t("navigation:menu.settings")}
                >
                  <SettingsIcon
                    className={cn(
                      "text-[22px] transition-colors",
                      isActive("/settings")
                        ? "text-[var(--nav-link)]"
                        : "text-[var(--secondary-text)]"
                    )}
                  />
                  {t("navigation:menu.settings")}
                </button>
              </li>
            )}
          </ul>
        </div>

        <div className="border-t border-[var(--glass-border)] p-8">
          <div className="text-center text-[13px] font-medium text-[var(--secondary-text)] opacity-60">
            © {new Date().getFullYear()} {t("navigation:brandName")}
          </div>
        </div>
      </nav>
    </div>,
    document.body
  )
}
