import type { ReactNode } from "react"

type DetailRowProps = {
  label: string
  value?: ReactNode
}

export const DetailRow = ({ label, value }: DetailRowProps) => {
  if (value == null || value === "") return null
  return (
    <div className="profile-detail-row grid grid-cols-[0.75rem_1fr] items-start gap-2 sm:gap-3 px-(--space-3) sm:px-(--space-4) py-2.5 sm:py-3 min-h-(--min-h-touch) sm:min-h-12 rounded-2xl transition-all duration-base border border-transparent hover:border-(--glass-border) hover:bg-(--bg-surface)/(--opacity-dim)">
      <div className="w-1.5 h-1.5 mt-2 rounded-full bg-(--brand-main) ring ring-(--brand-main)/20 justify-self-center" />
      <div className="text-xs sm:text-sm md:text-base leading-relaxed text-text-primary">
        <span className="font-bold text-(--brand-main) uppercase tracking-wider text-label-xs opacity-strong block mb-0.5">
          {label}
        </span>
        <span className="font-medium wrap-break-word">{value}</span>
      </div>
    </div>
  )
}

export default DetailRow
