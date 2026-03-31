import { motion } from "framer-motion"
import { Menu, X } from "lucide-react"
import { type NavbarLogicResult } from "./useNavbarLogic"
import { type NavbarMorphState } from "./useNavbarMorph"
import NotificationsBell from "@/components/feedback/NotificationsBell"
import MessengerButton from "@/components/layout/MessengerButton"
import SmartImage from "@/components/media/SmartImage"
import { DesktopNav } from "./DesktopNav"
import { UserMenu } from "./UserMenu"
import { NavbarOverflowMenu } from "./NavbarOverflowMenu"
import { springSoft } from "@/utils/animations"

interface NavbarActionsProps {
  logic: NavbarLogicResult
  morph: NavbarMorphState
}

export const NavbarActions = ({ logic, morph }: NavbarActionsProps) => {
  const {
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
    isActive,
    isSameTarget,
    scrollToTop,
    markScrollFromBottom,
    prefersReducedMotion,
    t,
    burgerBtnRef,
  } = logic

  const { isCompact, priorityLinks, overflowLinks } = morph

  if (isMobile) {
    return (
      <div className="ml-auto flex items-center gap-(--fluid-gap)">
        <MessengerButton />
        <NotificationsBell />
        {isAuth && user && !loading ? (
          <motion.div
            whileTap={prefersReducedMotion ? undefined : { scale: 0.95 }}
            transition={prefersReducedMotion ? { duration: 0 } : springSoft}
          >
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
          whileTap={prefersReducedMotion ? undefined : { scale: 0.9 }}
          transition={prefersReducedMotion ? { duration: 0 } : springSoft}
          type="button"
          className="flex shrink-0 cursor-pointer items-center justify-center rounded-2xl border border-(--glass-border) bg-(--bg-surface-hover)/(--opacity-subtle) p-0 shadow-sm backdrop-blur-md transition-all duration-base hover:bg-(--bg-surface-hover)/(--opacity-dim) size-touch text-text-primary"
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
              transition={prefersReducedMotion ? { duration: 0 } : { duration: 0.2 }}
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
              transition={prefersReducedMotion ? { duration: 0 } : { duration: 0.2 }}
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
        menuLinks={priorityLinks}
        isActive={isActive}
        isSameTarget={isSameTarget}
        scrollToTop={scrollToTop}
        markScrollFromBottom={markScrollFromBottom}
        prefersReducedMotion={prefersReducedMotion}
        isCompact={isCompact}
      />
      {overflowLinks.length > 0 && (
        <NavbarOverflowMenu
          items={overflowLinks}
          isActive={isActive}
          go={go}
          prefersReducedMotion={prefersReducedMotion}
          isCompact={isCompact}
        />
      )}
      <UserMenu
        user={user}
        isAuth={!!isAuth}
        loading={loading}
        go={go}
        t={t}
        isCompact={isCompact}
        prefersReducedMotion={prefersReducedMotion}
      />
    </>
  )
}
