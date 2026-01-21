import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import SettingsIcon from "@mui/icons-material/Settings"
import { cn } from "@/utils/cn"

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

  return (
    <div
      id="mobile-drawer"
      className={cn(
        "mobile-drawer fixed inset-0 z-[var(--ue-z-index-overlay)] flex h-screen w-screen",
        isOpen ? "pointer-events-auto bg-black/25" : "pointer-events-none bg-transparent",
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
          "fixed inset-y-0 left-0 z-[60] flex h-full w-[280px] max-w-[80%] flex-col bg-nav shadow-2xl transition-transform duration-300 ease-[cubic-bezier(0.32,0.72,0,1)]",
          "border-r border-transparent dark:border-white/10 dark:bg-slate-900/95 dark:backdrop-blur-xl",
          isOpen ? "translate-x-0" : "-translate-x-full"
        )}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex-1 overflow-y-auto px-3 py-6">
          <ul className="flex flex-col gap-1">
            {menuLinks.map((item) => {
              const Icon = item.icon
              const active = isActive(item.to)
              return (
                <li key={item.to}>
                  <Link
                    to={item.to}
                    onClick={onClose}
                    onFocus={(e) => {
                      if (!active) {
                        e.currentTarget.blur()
                      }
                    }}
                    className={cn(
                      "flex items-center gap-3 rounded-xl px-4 py-3 text-[15px] font-medium transition-all duration-200",
                      active
                        ? "bg-primary-main/10 text-primary-main dark:bg-primary-main/20 dark:text-white"
                        : "text-nav-text hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-white/5"
                    )}
                  >
                    {Icon && (
                      <Icon
                        className={cn(
                          "text-[20px] opacity-90 transition-colors",
                          active ? "text-primary-main dark:text-primary-light" : "text-slate-500"
                        )}
                      />
                    )}
                    {item.label}
                  </Link>
                </li>
              )
            })}
            {isAuth && user && (
              <li className="mt-2 border-t border-slate-100 pt-2 dark:border-white/10">
                <button
                  type="button"
                  className={cn(
                    "flex w-full items-center gap-3 rounded-xl px-4 py-3 text-[15px] font-medium transition-all duration-200",
                    isActive("/settings")
                      ? "bg-primary-main/10 text-primary-main dark:bg-primary-main/20 dark:text-white"
                      : "text-nav-text hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-white/5"
                  )}
                  onClick={(e) => {
                    e.stopPropagation()
                    onClose()
                    go("/settings")
                  }}
                  onFocus={(e) => {
                    if (!isActive("/settings")) {
                      e.currentTarget.blur()
                    }
                  }}
                  aria-label={t("navigation:menu.settings")}
                >
                  <SettingsIcon
                    className={cn(
                      "text-[20px] opacity-90 transition-colors",
                      isActive("/settings")
                        ? "text-primary-main dark:text-primary-light"
                        : "text-slate-500"
                    )}
                  />
                  {t("navigation:menu.settings")}
                </button>
              </li>
            )}
          </ul>
        </div>

        <div className="border-t border-slate-100 p-6 dark:border-white/10">
          <div className="text-center text-xs font-medium text-slate-400 dark:text-slate-500">
            © {new Date().getFullYear()} {t("navigation:brandName")}
          </div>
        </div>
      </nav>
    </div>
  )
}
