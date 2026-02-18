import { Link } from "react-router-dom"
import { motion } from "framer-motion"
import { type TFunction } from "i18next"
import guuLogo from "@/assets/guu_logo.png"
import SmartImage from "@/components/SmartImage"
import { cn } from "@/utils/cn"
import { breakpoints } from "@/theme/tokens"
import { hoverScale } from "@/utils/animations"

interface NavbarLogoProps {
  t: TFunction
  isMobile: boolean
  onLogoClick: (e: React.MouseEvent) => void
  markScrollFromBottom: () => void
}

export const NavbarLogo = ({ t, isMobile, onLogoClick, markScrollFromBottom }: NavbarLogoProps) => {
  return (
    <Link
      id="navbar-logo-link"
      to="/dashboard"
      aria-label={t("navigation:aria.homeLink")}
      className={cn(
        "inline-flex min-w-0 items-center rounded-2xl px-3 py-1.5 no-underline group transition-all duration-base hover:bg-(--bg-surface-hover)/(--opacity-soft)",
        isMobile ? "gap-fluid-gap" : "gap-4"
      )}
      onPointerDown={markScrollFromBottom}
      onClick={onLogoClick}
    >
      <motion.div
        variants={hoverScale}
        whileHover="hover"
        whileTap="tap"
        className="flex items-center justify-center shrink-0 rounded-full bg-(--bg-surface-raised) shadow-sm size-touch border border-border-subtle"
      >
        <SmartImage
          srcRaw={guuLogo}
          alt={t("navigation:brandAlt")}
          className="object-contain w-[65%] h-[65%]"
          loading="eager"
          fetchPriority="high"
          sizes={`(min-width: ${breakpoints.wide}) 2.75rem, (min-width: ${breakpoints.mobile}) 2.25rem, 1.625rem`}
          responsiveWidths={[28, 48, 64]}
          decoding="async"
        />
      </motion.div>
      <div className="flex flex-col justify-center">
        <span className="whitespace-nowrap font-black tracking-tight text-lg group-hover:opacity-strong transition-all duration-base leading-tight text-brand">
          {t("navigation:brandName")}
        </span>
      </div>
    </Link>
  )
}
