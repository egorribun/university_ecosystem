import { Link } from "@tanstack/react-router"
import { type TFunction } from "i18next"
import guuLogo from "@/assets/guu_logo.png"
import SmartImage from "@/components/media/SmartImage"
import { cn } from "@/utils/cn"
import { breakpoints } from "@/theme/tokens"

interface NavbarLogoProps {
  t: TFunction
  isMobile: boolean
  isCompact: boolean
  isPhone: boolean
  prefersReducedMotion: boolean
  onLogoClick: (e: React.MouseEvent) => void
  markScrollFromBottom: () => void
}

/**
 * NavbarLogo — all transitions use CSS only (no Framer Motion).
 * Every child shares the same 500ms ease-premium timing as the pill container,
 * preventing the "logo jumps ahead of pill" desync.
 */
export const NavbarLogo = ({
  t,
  isMobile,
  isCompact,
  isPhone,
  prefersReducedMotion,
  onLogoClick,
  markScrollFromBottom,
}: NavbarLogoProps) => {
  const dur = prefersReducedMotion ? "duration-0" : "duration-500"
  const ease = "ease-[var(--ease-premium)]"

  return (
    <Link
      id="navbar-logo-link"
      to="/dashboard"
      aria-label={t("navigation:aria.homeLink")}
      className={cn(
        "inline-flex min-w-0 items-center rounded-2xl no-underline group",
        "transition-[transform,opacity]",
        dur,
        ease,
        "hover:bg-(--bg-surface-hover)/(--opacity-soft)",
        isCompact
          ? "gap-0 px-1 py-1"
          : isPhone
            ? "gap-0 px-1 py-1"
            : isMobile
              ? "gap-fluid-gap px-3 py-1.5"
              : "gap-3 px-3 py-1.5"
      )}
      onPointerDown={markScrollFromBottom}
      onClick={onLogoClick}
    >
      {/* Logo circle — CSS transition synced with pill + shimmer on load */}
      <div
        className={cn(
          "flex items-center justify-center shrink-0 rounded-full",
          "bg-(--bg-surface-raised) dark:bg-(--bg-surface-hover) shadow-sm border border-border-subtle",
          "transition-[transform,opacity]",
          dur,
          ease,
          isCompact
            ? "w-8 h-8"
            : isPhone
              ? "w-(--nav-action-size) h-(--nav-action-size)"
              : "w-11 h-11",
          !prefersReducedMotion &&
            "hover:scale-105 active:scale-95 hover:transition-transform hover:duration-200"
        )}
      >
        <SmartImage
          srcRaw={guuLogo}
          alt={t("navigation:brandAlt")}
          className="object-contain w-3/4 h-3/4"
          loading="eager"
          fetchPriority="high"
          sizes={`(min-width: ${breakpoints.wide}) 2.75rem, (min-width: ${breakpoints.mobile}) 2.25rem, 1.625rem`}
          responsiveWidths={[28, 48, 64]}
          decoding="async"
        />
      </div>

      {/* Brand text — instant hide/show, pill morph handles the visual transition */}
      <div
        className={cn(
          "overflow-hidden",
          isCompact || isPhone ? "max-w-0 opacity-0" : "max-w-40 opacity-100"
        )}
      >
        <span className="whitespace-nowrap font-black tracking-tight text-lg leading-tight text-text-primary">
          {t("navigation:brandName")}
        </span>
      </div>
    </Link>
  )
}
