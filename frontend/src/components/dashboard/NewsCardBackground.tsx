import { memo, type FC } from "react"

// Wave 43→45: CSS @keyframes, slowed + softened orbs
export const NewsCardBackground: FC = memo(function NewsCardBackground() {
  return (
    <>
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 z-hide mix-blend-soft-light opacity-medium transition-opacity duration-slow motion-reduce:!animate-none"
        style={{
          background:
            "radial-gradient(circle at top right, var(--dash-card-news-radial), transparent 68%)",
          animation: "orb-breathe 6s ease-in-out infinite",
        }}
      />
      <span
        aria-hidden="true"
        className="pointer-events-none absolute -bottom-12 left-1/3 z-hide h-40 w-40 rounded-full opacity-medium blur-3xl mix-blend-soft-light transition-opacity duration-slower motion-reduce:!animate-none"
        style={{
          background: "radial-gradient(circle, var(--dash-card-news-orb), transparent)",
          animation: "orb-drift 8.5s ease-in-out infinite",
        }}
      />
    </>
  )
})

export default NewsCardBackground
