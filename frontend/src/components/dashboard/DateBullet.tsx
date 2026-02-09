import { useTranslation } from "react-i18next"
import { Tooltip } from "@/components/ui"
import { cn } from "@/utils/cn"
import { pad } from "@/utils/scheduleUtils"

interface DateBulletProps {
  date?: string
  locale: string
}

export function DateBullet({ date, locale }: DateBulletProps) {
  const { t } = useTranslation("common")
  const d = date ? new Date(date) : null
  const dd = d ? pad(d.getDate()) : "—"
  const mm = d ? pad(d.getMonth() + 1) : "--"
  const fallback = t("dateUnknown")
  const full = d
    ? d.toLocaleString(locale, {
        day: "2-digit",
        month: "long",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : fallback
  return (
    <Tooltip content={full}>
      <span
        aria-label={t("ariaDatePublished", { date: full })}
        className={cn(
          "flex h-11 w-11 min-h-11 min-w-11 flex-col items-center justify-center rounded-full border border-brand/20 bg-brand/5 text-brand shadow-sm dark:bg-brand/10",
          "shadow-sm"
        )}
      >
        <span className="text-[0.85rem] font-black leading-none tracking-tight">{dd}</span>
        <span className="text-[0.65rem] font-semibold leading-tight text-(--text-secondary)/70">
          {mm}
        </span>
      </span>
    </Tooltip>
  )
}





