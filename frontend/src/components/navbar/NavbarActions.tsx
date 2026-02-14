import { motion } from "framer-motion"
import { Menu, X } from "lucide-react"
import { type TFunction } from "i18next"
import { type ScrollBehavior } from "@/hooks/useScrollRestoration"
import NotificationsBell from "@/components/NotificationsBell"
import MessengerButton from "@/components/MessengerButton"
import SmartImage from "@/components/SmartImage"
import { DesktopNav } from "./DesktopNav"
import { UserMenu } from "./UserMenu"
import { springSoft } from "@/utils/animations"
import { type NavigationItem } from "@/config/navigation"
import { type User } from "@/types/User"

interface NavbarActionsProps {
  isMobile: boolean
  mobileMenu: boolean
  setMobileMenu: (v: boolean | ((v: boolean) => boolean)) => void
  isAuth: boolean
  user: User | null
  loading: boolean
  avatarSource: string
  avatarFallback: string
  avatarCacheV?: number
  profileAlt: string
  profileTitle: string
  go: (to: string) => void
  // Desktop specific
  menuLinks: NavigationItem[]
  isActive: (to: string) => boolean
  isSameTarget: (to: string) => boolean
  scrollToTop: (behavior?: ScrollBehavior) => void
  markScrollFromBottom: () => void
  prefersReducedMotion: boolean
  t: TFunction
  burgerBtnRef: React.RefObject<HTMLButtonElement | null>
}

export const NavbarActions = ({
  isMobile,
  mobileMenu,
  setMobileMenu,
  isAuth,
  user,
  loading,
  avatarSource,
  avatarFallback,
  avatarCacheV,
  profileAlt,
  profileTitle,
  go,
  menuLinks,
  isActive,
  isSameTarget,
  scrollToTop,
  markScrollFromBottom,
  prefersReducedMotion,
  t,
  burgerBtnRef,
}: NavbarActionsProps) => {
  if (isMobile) {
    return (
      <div className="ml-auto flex items-center gap-(--fluid-gap)">
        <MessengerButton />
        <NotificationsBell />
        {isAuth && user && !loading ? (
          <motion.div whileTap={{ scale: 0.95 }} transition={springSoft}>
            <SmartImage
              cacheV={avatarSource ? avatarCacheV : undefined}
              fallback={avatarFallback}
              alt={profileAlt}
              title={profileTitle}
              className="block cursor-pointer rounded-full border-2 border-brand/(--opacity-medium) shadow-sm object-cover w-9 h-9 shrink-0"
              onClick={() => go("/profile")}
            />
          </motion.div>
        ) : (
          <div className="rounded-full shrink-0 w-9 h-9 bg-brand/(--opacity-soft) animate-pulse" />
        )}
        <motion.button
          whileTap={{ scale: 0.9 }}
          transition={springSoft}
          type="button"
          className="flex shrink-0 cursor-pointer items-center justify-center rounded-2xl border border-(--glass-border) bg-(--bg-surface-hover)/(--opacity-subtle) p-0 shadow-sm backdrop-blur-md transition-all duration-300 hover:bg-(--bg-surface-hover)/(--opacity-dim) size-touch text-(--text-primary)"
          onClick={() => setMobileMenu((v) => !v)}
          aria-label={mobileMenu ? t("navigation:aria.closeMenu") : t("navigation:aria.openMenu")}
          aria-expanded={mobileMenu}
          aria-controls="mobile-drawer"
          ref={burgerBtnRef}
        >
          <div className="relative w-6 h-6 flex items-center justify-center">
            <motion.div
              initial={false}
              animate={{
                opacity: mobileMenu ? 0 : 1,
                rotate: mobileMenu ? 90 : 0,
                scale: mobileMenu ? 0.5 : 1,
              }}
              transition={{ duration: 0.2 }}
              className="absolute inset-0 flex items-center justify-center"
            >
              <Menu className="w-6 h-6 stroke-(--text-primary)" strokeWidth={2.5} />
            </motion.div>
            <motion.div
              initial={false}
              animate={{
                opacity: mobileMenu ? 1 : 0,
                rotate: mobileMenu ? 0 : -90,
                scale: mobileMenu ? 1 : 0.5,
              }}
              transition={{ duration: 0.2 }}
              className="absolute inset-0 flex items-center justify-center"
            >
              <X className="w-6 h-6 stroke-(--text-primary)" strokeWidth={2.5} />
            </motion.div>
          </div>
        </motion.button>
      </div>
    )
  }

  return (
    <>
      <DesktopNav
        menuLinks={menuLinks}
        isActive={isActive}
        isSameTarget={isSameTarget}
        scrollToTop={scrollToTop}
        markScrollFromBottom={markScrollFromBottom}
        prefersReducedMotion={prefersReducedMotion}
      />
      <UserMenu user={user} isAuth={!!isAuth} loading={loading} go={go} t={t} />
    </>
  )
}
