import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import SettingsIcon from "@mui/icons-material/Settings";
import { cn } from "@/utils/cn";

interface MenuLink {
    to: string;
    label: string;
    icon?: React.ElementType;
}

interface MobileMenuProps {
    isOpen: boolean;
    onClose: () => void;
    menuLinks: MenuLink[];
    isActive: (to: string) => boolean;
    go: (to: string) => void;
    user: any;
    isAuth: boolean;
    prefersReducedMotion: boolean;
    drawerTrapRef: React.RefObject<HTMLDivElement>;
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
    const { t } = useTranslation(["navigation"]);

    if (!isOpen) return null;

    return (
        <div
            id="mobile-drawer"
            className={cn(
                "fixed inset-0 z-[var(--ue-z-index-overlay)] flex h-screen w-screen",
                isOpen ? "pointer-events-auto bg-black/25" : "pointer-events-none bg-transparent",
                !prefersReducedMotion && "transition-[background] duration-200"
            )}
            onClick={onClose}
            role="dialog"
            aria-modal="true"
            aria-label={t("navigation:aria.mobileMenu")}
        >
            <nav
                ref={drawerTrapRef}
                className={cn(
                    "mobile-drawer-content", // Keep existing class for specific styles if needed, or replace
                    "flex h-full w-[80%] max-w-[320px] flex-col bg-[var(--nav-bg)] shadow-2xl",
                    !prefersReducedMotion && "transition-transform duration-300 ease-out",
                    isOpen ? "translate-x-0" : "-translate-x-full"
                )}
                style={{
                    // Fallback for transition if class not enough or specific logic
                    transform: isOpen ? "translateX(0)" : "translateX(-120%)"
                }}
                onClick={(e) => e.stopPropagation()}
            >
                <ul className="flex flex-1 flex-col gap-2 overflow-y-auto p-0 w-full list-none m-0">
                    {menuLinks.map((item) => {
                        const Icon = item.icon;
                        const active = isActive(item.to);
                        return (
                            <li key={item.to}>
                                <Link
                                    to={item.to}
                                    onClick={onClose}
                                    onFocus={(e) => {
                                        if (!active) {
                                            e.currentTarget.blur();
                                        }
                                    }}
                                    className={cn(
                                        "menu-link", // Keep existing class
                                        active && "active"
                                    )}
                                >
                                    {Icon && (
                                        <Icon
                                            style={{
                                                fontSize: "20px",
                                                opacity: 0.9,
                                            }}
                                        />
                                    )}
                                    {item.label}
                                </Link>
                            </li>
                        );
                    })}
                    {isAuth && user && (
                        <li className="mt-1">
                            <button
                                type="button"
                                className={cn(
                                    "menu-link cursor-pointer",
                                    isActive("/settings") && "active"
                                )}
                                onClick={(e) => {
                                    e.stopPropagation();
                                    onClose();
                                    go("/settings");
                                }}
                                onFocus={(e) => {
                                    if (!isActive("/settings")) {
                                        e.currentTarget.blur();
                                    }
                                }}
                                aria-label={t("navigation:menu.settings")}
                            >
                                <SettingsIcon
                                    style={{
                                        fontSize: "20px",
                                        opacity: 0.9,
                                    }}
                                />
                                {t("navigation:menu.settings")}
                            </button>
                        </li>
                    )}
                </ul>

                <div className="mobile-drawer-footer">
                    <div className="mobile-drawer-copyright">
                        © {new Date().getFullYear()} {t("navigation:brandName")}
                    </div>
                </div>
            </nav>
        </div>
    );
}
