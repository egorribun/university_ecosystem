import { cn } from "@/utils/cn"
import { MobileMenu } from "./MobileMenu"
import { NavbarLogo } from "./NavbarLogo"
import { NavbarActions } from "./NavbarActions"
import { useNavbarLogic } from "./useNavbarLogic"
import { NavbarPill } from "./NavbarPill"
import { useNavbarMorph } from "./useNavbarMorph"

/**
 * Navbar — sticky, FIXED HEIGHT in all states.
 *
 * CRITICAL: The <nav> never changes height. Changing height on a sticky
 * element causes layout shift (page content jumps). Instead, the pill
 * container inside visually morphs while the nav shell stays constant.
 * This is the same technique Apple.com uses for their sticky nav.
 */
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

  const morph = useNavbarMorph(menuLinks, {
    isScrolled,
    viewport: logic.viewport,
    prefersReducedMotion,
  })

  // Desktop: full morph to pill. Mobile: just glass bg on scroll (no pill).
  const showPill = morph.isCompact && !isMobile

  return (
    <>
      <nav
        ref={navRef}
        style={{ boxShadow: "none" }}
        className={cn(
          "vt-navbar sticky top-0 z-(--z-navbar) w-full",
          // FIXED height — never changes, no layout shift
          "h-(--navbar-height)",
          "flex items-center justify-center",
          showPill
            ? "bg-transparent"
            : isScrolled && isMobile
              ? "bg-(--pill-bg)"
              : "bg-nav/(--opacity-hover)"
        )}
      >
        <NavbarPill isCompact={showPill} prefersReducedMotion={prefersReducedMotion}>
          <NavbarLogo
            t={t}
            isMobile={isMobile}
            isCompact={showPill}
            isPhone={morph.isPhone}
            prefersReducedMotion={prefersReducedMotion}
            onLogoClick={(e) => {
              if (isSameTarget("/dashboard")) {
                e.preventDefault()
                scrollToTop(prefersReducedMotion ? "auto" : "smooth")
              }
            }}
            markScrollFromBottom={markScrollFromBottom}
          />

          <NavbarActions logic={logic} morph={morph} />
        </NavbarPill>
      </nav>

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
