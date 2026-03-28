import { Link } from "@tanstack/react-router"
import { motion } from "framer-motion"
import { cn } from "@/utils/cn"
import { slideUpVariants, staggerContainerVariants, springSoft } from "@/utils/animations"
import { type NavigationItem } from "@/config/navigation"
import { type ScrollBehavior } from "@/hooks/useScrollRestoration"

interface DesktopNavProps {
  menuLinks: NavigationItem[]
  isActive: (to: string) => boolean
  isSameTarget: (to: string) => boolean
  scrollToTop: (behavior?: ScrollBehavior) => void
  markScrollFromBottom: () => void
  prefersReducedMotion: boolean
}

export const DesktopNav = ({
  menuLinks,
  isActive,
  isSameTarget,
  scrollToTop,
  markScrollFromBottom,
  prefersReducedMotion,
}: DesktopNavProps) => {
  return (
    <motion.ul
      variants={staggerContainerVariants(0.05, 0.2)}
      initial="hidden"
      animate="visible"
      className="ml-(--space-8) flex flex-1 flex-row flex-wrap items-center gap-1 m-0 p-0 min-w-0 list-none text-base font-medium"
    >
      {menuLinks.map((item) => (
        <motion.li
          key={item.to}
          variants={slideUpVariants}
          whileHover={{ y: -1 }}
          whileTap={{ scale: 0.98 }}
        >
          <Link
            id={`navbar-link-${item.to.replace(/\//g, "") || "home"}`}
            to={item.to}
            className={cn("menu-link", isActive(item.to) && "active")}
            onPointerDown={markScrollFromBottom}
            onClick={(e) => {
              if (isSameTarget(item.to)) {
                e.preventDefault()
                scrollToTop(prefersReducedMotion ? "auto" : "smooth")
              }
            }}
          >
            <span className="relative z-surface transition-colors duration-fast">{item.label}</span>
            {isActive(item.to) && (
              <motion.div
                layoutId="navbar-active-bar"
                className="active-bar"
                transition={springSoft}
              />
            )}
          </Link>
        </motion.li>
      ))}
    </motion.ul>
  )
}
