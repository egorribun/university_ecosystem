import { motion } from "framer-motion"
import { memo } from "react"

export const NewsCardBackground = memo(function NewsCardBackground() {
  return (
    <>
      <motion.span
        aria-hidden="true"
        initial={{ opacity: 0 }}
        whileHover={{ opacity: "var(--opacity-heavy)" }}
        animate={{
          scale: [1, 1.1, 1],
        }}
        transition={{
          duration: 4.5,
          repeat: Infinity,
          ease: "easeInOut",
        }}
        className="pointer-events-none absolute inset-0 z-hide bg-[radial-gradient(circle_at_top_right,var(--dash-card-news-radial),transparent_68%)] mix-blend-soft-light transition-opacity duration-slow"
      />
      <motion.span
        aria-hidden="true"
        initial={{ opacity: "var(--opacity-medium)" }}
        whileHover={{ opacity: "var(--opacity-strong)" }}
        animate={{
          scale: [1, 1.18, 1],
          rotate: [0, -5, 0],
          x: [0, 10, 0],
        }}
        transition={{
          duration: 6.5,
          repeat: Infinity,
          ease: "easeInOut",
        }}
        className="pointer-events-none absolute -bottom-20 left-1/3 z-hide h-44 w-44 rounded-full bg-[radial-gradient(circle,var(--dash-card-news-orb),transparent)] blur-3xl mix-blend-soft-light transition-opacity duration-slower"
      />
    </>
  )
})
