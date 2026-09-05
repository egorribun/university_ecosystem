import { m } from "framer-motion"
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
      <div className="ml-auto flex items-center gap-(--nav-action-gap)">
        <MessengerButton />
        <NotificationsBell />
        {isAuth && user && !loading ? (
          <m.button
            type="button"
            aria-label={profileTitle}
            title={profileTitle}
            className="flex size-11 items-center justify-center rounded-full border-none bg-transparent p-0"
            onClick={() => go("/profile")}
            whileTap={prefersReducedMotion ? undefined : { scale: 0.95 }}
            transition={prefersReducedMotion ? { duration: 0 } : springSoft}
          >
            <SmartImage
              srcRaw={avatarSource || undefined}
              cacheV={avatarSource ? avatarCacheV : undefined}
              fallback={avatarFallback}
              alt={profileAlt}
              title={profileTitle}
              className="pointer-events-none block size-8 shrink-0 rounded-full border-2 border-brand/(--opacity-medium) object-cover"
            />
          </m.button>
        ) : (
          <div className="size-11 shrink-0 rounded-full bg-brand/(--opacity-soft) animate-pulse" />
        )}
        <button
          type="button"
          className="nav-action-btn cursor-pointer text-text-primary"
          onClick={() => setMobileMenu((v) => !v)}
          aria-label={mobileMenu ? t("navigation:aria.closeMenu") : t("navigation:aria.openMenu")}
          aria-expanded={mobileMenu}
          aria-controls="mobile-drawer"
          ref={burgerBtnRef}
        >
          <div className="relative flex items-center justify-center nav-action-icon">
            <m.div
              initial={false}
              animate={{
                opacity: mobileMenu ? 0 : 1,
                rotate: mobileMenu ? 90 : 0,
                scale: mobileMenu ? 0.5 : 1,
              }}
              transition={prefersReducedMotion ? { duration: 0 } : { duration: 0.2 }}
              className="absolute inset-0 flex items-center justify-center"
            >
              <Menu className="nav-action-icon stroke-(--text-primary)" strokeWidth={2.5} />
            </m.div>
            <m.div
              initial={false}
              animate={{
                opacity: mobileMenu ? 1 : 0,
                rotate: mobileMenu ? 0 : -90,
                scale: mobileMenu ? 1 : 0.5,
              }}
              transition={prefersReducedMotion ? { duration: 0 } : { duration: 0.2 }}
              className="absolute inset-0 flex items-center justify-center"
            >
              <X className="nav-action-icon stroke-(--text-primary)" strokeWidth={2.5} />
            </m.div>
          </div>
        </button>
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
