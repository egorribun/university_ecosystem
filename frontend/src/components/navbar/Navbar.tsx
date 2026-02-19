import { motion } from "framer-motion"
import { cn } from "@/utils/cn"
import { motion as motionTokens } from "@/theme/tokens"
import { EASING } from "@/utils/motion"
import { MobileMenu } from "./MobileMenu"
import { NavbarLogo } from "./NavbarLogo"
import { NavbarActions } from "./NavbarActions"
import { useNavbarLogic } from "./useNavbarLogic"

const Navbar = () => {
  const logic = useNavbarLogic()
  const {
    navRef,
    isScrolled,
    prefersReducedMotion,
    isMobile,
    markScrollFromBottom,
    isSameTarget,
    scrollToTop,
    mobileMenu,
    setMobileMenu,
    drawerTrapRef,
    menuLinks,
    isActive,
    isAuth,
    user,
    go,
    t,
  } = logic

  return (
    <>
      <motion.nav
        ref={navRef}
        initial={{ y: -100, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: motionTokens.navTransition, ease: EASING.premium }}
        className={cn(
          "sticky top-0 z-navbar w-full flex flex-col justify-center",
          "border-b border-glass-border transition-all duration-slow",
          isScrolled
            ? "bg-nav/(--opacity-hover) shadow-glass backdrop-nav h-(--navbar-height-scrolled)"
            : "bg-transparent h-(--navbar-height)",
          "items-center",
          "pt-(--safe-area-top)",
          prefersReducedMotion && "transition-none"
        )}
      >
        <div className="flex h-full w-full items-center px-fluid-x box-border">
          <NavbarLogo
            t={t}
            isMobile={isMobile}
            onLogoClick={(e) => {
              if (isSameTarget("/dashboard")) {
                e.preventDefault()
                scrollToTop(prefersReducedMotion ? "auto" : "smooth")
              }
            }}
            markScrollFromBottom={markScrollFromBottom}
          />

          <NavbarActions logic={logic} />
        </div>
      </motion.nav>

      {isMobile && (
        <MobileMenu
          isOpen={mobileMenu}
          onClose={() => setMobileMenu(false)}
          menuLinks={menuLinks}
          isActive={isActive}
          go={go}
          user={user}
          isAuth={Boolean(isAuth)}
          prefersReducedMotion={prefersReducedMotion}
          drawerTrapRef={drawerTrapRef}
        />
      )}
    </>
  )
}

export default Navbar
