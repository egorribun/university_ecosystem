import type { User } from "@/types/User"
import { useTranslation } from "react-i18next"
import { useMemo } from "react"
import { Badge } from "@/components/ui"
import WeatherWidget from "@/components/ui/WeatherWidget"
import { Sparkles } from "lucide-react"
import { useGreeting } from "@/hooks/useGreeting"
import { nowParity } from "@/utils/scheduleUtils"

/** Wave 49: Calculate ISO week number */
function getISOWeekNumber(date: Date): number {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()))
  d.setUTCDate(d.getUTCDate() + 4 - (d.getUTCDay() || 7))
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1))
  return Math.ceil(((+d - +yearStart) / 86400000 + 1) / 7)
}

interface DashboardHeroProps {
  user: User | null
  time: Date
  hh: string
  mm: string
  dateStr: string
  isNarrow: boolean
  prefersReducedMotion: boolean
  /** Wave 54: Stories slot — rendered inside hero flex-row at ≥1220px */
  storiesSlot?: React.ReactNode
}

export function DashboardHero({ user, time, hh, mm, dateStr, storiesSlot }: DashboardHeroProps) {
  const { t } = useTranslation(["dashboard", "common"])
  const { greeting, greetingKey, specialKey, emoji } = useGreeting(time)

  // Wave 49: Academic week number + parity (replaces day progress ring)
  const weekNumber = useMemo(() => getISOWeekNumber(time), [time])
  const parity = nowParity()

  return (
    <section className="relative flex w-full flex-col px-4 pb-3 pt-5 text-text-primary sm:px-6 md:px-10 lg:px-14 min-h-[260px]">
      <div className="relative z-deep">
        <header
          className={`glass-noise relative rounded-xl border border-(--dash-border) px-8 py-8 md:px-10 md:py-9 greeting-${greetingKey}`}
          style={{
            background: "var(--hero-card-bg)",
            boxShadow:
              "0 1px 3px color-mix(in srgb, black 8%, transparent), 0 4px 16px color-mix(in srgb, black 6%, transparent), inset 0 1px 0 color-mix(in srgb, white 4%, transparent)",
          }}
        >
          <span
            className="pointer-events-none absolute inset-x-[20%] top-0 z-10 h-px"
            style={{ background: "var(--dash-accent-line)", opacity: 0.5 }}
            aria-hidden="true"
          />

          {/* Wave 54: flex-row at ≥1220px — greeting left, stories right */}
          <div className="relative flex flex-col gap-4 min-[1220px]:flex-row min-[1220px]:items-center min-[1220px]:gap-6">
            <div className="shrink-0 space-y-4">
              <h1
                className="font-display font-extrabold leading-[1.15] tracking-tight min-h-[2lh]"
                style={{ fontSize: "clamp(1.75rem, 3vw, 2.75rem)" }}
              >
                {specialKey && (
                  <span className="mr-2 inline-flex text-amber-400">
                    <Sparkles className="h-8 w-8" aria-hidden="true" />
                  </span>
                )}
                {greeting}
                {user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""}!
                {emoji && (
                  <span className="ml-2 inline-block" aria-hidden="true">
                    {emoji}
                  </span>
                )}
              </h1>
              <div
                className="flex min-h-[40px] flex-wrap items-center gap-x-4 gap-y-2"
                role="status"
                aria-live="polite"
              >
                <Badge
                  size="sm"
                  className="shrink-0 border-(--dash-border) bg-white/(--opacity-faint) font-mono text-text-primary"
                  aria-label={t("common:ariaCurrentTime")}
                >
                  <span className="flex items-baseline gap-1.5 font-mono text-xl leading-none tabular-nums">
                    <span>{hh}</span>
                    <span aria-hidden="true" className="inline-block opacity-soft">
                      :
                    </span>
                    <span>{mm}</span>
                  </span>
                </Badge>
                <span className="shrink-0 text-base font-medium opacity-heavy">
                  {t("dashboard:academicWeek", { week: weekNumber })}
                  {" · "}
                  <span className="text-brand">
                    {parity === "even" ? t("dashboard:parityEven") : t("dashboard:parityOdd")}
                  </span>
                </span>
                <WeatherWidget className="shrink-0" />
                <span className="text-base font-medium opacity-heavy">{dateStr}</span>
              </div>
            </div>

            {/* Wave 54: Stories — flex-1 with min-w-0 for scroll, NO overflow-hidden (FIX-54-01) */}
            {storiesSlot && (
              <div className="relative z-10 min-[1220px]:flex-1 min-[1220px]:min-w-0 min-[1220px]:self-center">
                {storiesSlot}
              </div>
            )}
          </div>
        </header>
      </div>
    </section>
  )
}
