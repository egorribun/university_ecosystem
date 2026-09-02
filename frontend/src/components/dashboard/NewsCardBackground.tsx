import { memo, type FC } from "react"

export const NewsCardBackground: FC = memo(function NewsCardBackground() {
  return (
    <span
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 z-hide opacity-soft"
      style={{
        background:
          "linear-gradient(135deg, color-mix(in srgb, var(--dash-card-news-radial) 22%, transparent), transparent 72%)",
      }}
    />
  )
})

export default NewsCardBackground
