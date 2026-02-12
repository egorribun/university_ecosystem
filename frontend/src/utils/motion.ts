// Common easing curves matching src/styles/theme.css
export const EASING = {
  premium: [0.16, 1, 0.3, 1] as const, // --ease-premium
  card: [0.22, 0.61, 0.36, 1] as const, // --animate-card-hover (custom bezier)
  springSoft: {
    type: "spring",
    stiffness: 400,
    damping: 30,
  } as const,
}

export const DURATIONS = {
  fast: 0.2, // --transition-fast (approx)
  medium: 0.4,
  slow: 0.5, // --transition-premium (approx)
}

export const ANIMATION_VARIANTS = {
  fadeIn: {
    initial: { opacity: 0 },
    animate: { opacity: 1 },
    exit: { opacity: 0 },
  },
  scaleIn: {
    initial: { opacity: 0, scale: 0.95 },
    animate: { opacity: 1, scale: 1 },
    exit: { opacity: 0, scale: 0.95 },
  },
}
