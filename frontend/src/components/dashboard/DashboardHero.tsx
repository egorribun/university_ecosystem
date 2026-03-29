import type { User } from "@/types/User"
// useNavigate removed — profile button removed (accessible via navbar)
import { useTranslation } from "react-i18next"
import { Badge } from "@/components/ui"
import WeatherWidget from "@/components/ui/WeatherWidget"
import { ScrollReveal } from "@/components/motion/ScrollReveal"
import { cn } from "@/utils/cn"
import { useGreeting } from "@/hooks/useGreeting"

interface DashboardHeroProps {
  user: User | null
  time: Date
  hh: string
  mm: string
  dateStr: string
  isNarrow: boolean
  prefersReducedMotion: boolean
}

export function DashboardHero({
  user,
  time,
  hh,
  mm,
  dateStr,
  isNarrow,
  prefersReducedMotion,
}: DashboardHeroProps) {
  const { t } = useTranslation(["dashboard", "common"])
  const { greeting } = useGreeting(time)

  const showHeaderMotion = !prefersReducedMotion && !isNarrow

  return (
    <section className="relative flex w-full flex-col px-4 pb-3 pt-5 text-text-primary sm:px-6 md:px-10 lg:px-14">
      <div className="relative z-deep">
        <ScrollReveal mode="pop" delay={0.1} width="100%">
          <header
            className={cn(
              "group glass-noise relative rounded-xl transition-all duration-slow ease-back-out",
              "border border-(--dash-border)",
              "hover:-translate-y-0.5 motion-reduce:hover:transform-none",
              "px-8 py-8 md:px-10 md:py-9"
            )}
            style={{
              background: "var(--hero-card-bg)",
              boxShadow: "0 1px 3px color-mix(in srgb, black 8%, transparent), 0 4px 16px color-mix(in srgb, black 6%, transparent), inset 0 1px 0 color-mix(in srgb, white 4%, transparent)",
            }}
          >
            {/* Blue accent line at top */}
            <span
              aria-hidden="true"
              className="pointer-events-none absolute inset-x-[20%] top-0 z-10 h-px"
              style={{ background: "var(--dash-accent-line)", opacity: 0.5 }}
            />

            {/* Shimmer on hover */}
            {showHeaderMotion && (
              <span
                aria-hidden="true"
                className="pointer-events-none absolute -inset-y-24 -left-1 w-[170%] skew-x-[-18deg] bg-linear-to-r from-transparent via-white/(--opacity-dim) to-transparent opacity-0 transition-all duration-slower ease-out group-hover:translate-x-[35%] group-hover:opacity-soft"
              />
            )}

            {/* Decorative flare — top right corner glow */}
            <div className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full bg-(--flare-highlight) blur-3xl opacity-soft" />

            {/* Spinning conic gradient orb */}
            {showHeaderMotion && (
              <div className="pointer-events-none absolute left-[-8%] top-[-25%] h-[8rem] w-[8rem] animate-[spin_40s_linear_infinite] rounded-full bg-(--grad-dash-conic) opacity-soft blur-3xl will-change-transform" />
            )}

            <div className="relative flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div className="space-y-4">
                {/* Inline fontSize — CSS var override unreliable across @layer boundaries */}
                <h1
                  className="font-display font-extrabold leading-[1.15] tracking-tight"
                  style={{ fontSize: "clamp(2.25rem, 4vw, 3.75rem)" }}
                >
                  {greeting}
                  {user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""}!
                </h1>
                <div
                  className="flex flex-wrap items-center gap-x-4 gap-y-2"
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
                      <span aria-hidden="true" className="inline-block animate-dash-colon-blink opacity-soft">:</span>
                      <span>{mm}</span>
                    </span>
                  </Badge>
                  <WeatherWidget className="shrink-0" />
                  <span className="text-base font-medium opacity-heavy">
                    {dateStr}
                  </span>
                </div>
              </div>

              {/* Profile button removed — accessible via navbar */}
            </div>
          </header>
        </ScrollReveal>
      </div>
    </section>
  )
}
