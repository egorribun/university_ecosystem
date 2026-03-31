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

  const morph = useNavbarMorph(menuLinks)

  // Desktop: full morph to pill. Mobile: just glass bg on scroll (no pill).
  const showPill = morph.isCompact && !isMobile

  const dur = prefersReducedMotion ? "duration-0" : "duration-500"
  const ease = "ease-[var(--ease-premium)]"

  return (
    <>
      <nav
        ref={navRef}
        className={cn(
          "vt-navbar sticky top-0 z-(--z-navbar) w-full",
          // FIXED height — never changes, no layout shift
          "h-(--navbar-height)",
          "flex items-center justify-center",
          // Only visual properties transition (no height, no padding)
          "transition-[background,border-color,backdrop-filter,box-shadow]",
          dur, ease,
          showPill
            ? [
                // Desktop scrolled: transparent shell, pill provides visual bg
                "bg-transparent border-b border-transparent",
              ]
            : isScrolled && isMobile
              ? [
                  // Mobile scrolled: glass bg on full-width nav
                  "bg-(--pill-bg) backdrop-blur-xl backdrop-saturate-[1.4]",
                  "border-b border-(--pill-border) shadow-[var(--pill-shadow)]",
                ]
              : [
                  // Default: full-width glass nav
                  "bg-nav/(--opacity-hover) backdrop-blur-(--blur-xl)",
                  "border-b border-glass-border",
                ]
        )}
      >
        <NavbarPill isCompact={showPill} prefersReducedMotion={prefersReducedMotion}>
          <NavbarLogo
            t={t}
            isMobile={isMobile}
            isCompact={showPill}
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
