import { useMemo, type ReactNode } from "react"
import type { User } from "@/types/User"
import { useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { motion } from "framer-motion"
import { Badge, Button } from "@/components/ui"
import WeatherWidget from "@/components/WeatherWidget"
import Magnetic from "@/components/Magnetic"
import { ScrollReveal } from "@/components/ScrollReveal"
import { cn } from "@/utils/cn"

interface DashboardHeroProps {
  user: User | null
  time: Date
  hh: string
  mm: string
  dateStr: string
  isNarrow: boolean
  prefersReducedMotion: boolean
  children?: ReactNode
}

function getGreetingKey(hour: number): "morning" | "afternoon" | "evening" | "night" {
  if (hour >= 4 && hour < 12) return "morning"
  if (hour >= 12 && hour < 17) return "afternoon"
  if (hour >= 17 && hour <= 23) return "evening"
  return "night"
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
  const navigate = useNavigate()
  const { t } = useTranslation(["dashboard", "common", "navigation"])

  const greetingKey = useMemo(() => getGreetingKey(time.getHours()), [time])
  const greeting = t(`dashboard:greeting.${greetingKey}`)

  const headerGradientClass = cn(
    "transition-[background] duration-700",
    isNarrow
      ? "bg-(--grad-header-135)"
      : "bg-(--grad-header-125)"
  )

  const heroBackdropLayers = useMemo(() => {
    const layers = [
      "absolute inset-0 z-(--z-hide) bg-[radial-gradient(circle_at_top,var(--dash-hero-radial-top),transparent_78%)] mix-blend-soft-light",
      "absolute inset-0 z-(--z-hide) bg-[radial-gradient(circle_at_bottom,var(--dash-hero-radial-bottom),transparent_78%)]",
    ]

    const orbSize = isNarrow ? "h-[28rem] w-[28rem]" : "h-[46rem] w-[46rem]"
    layers.push(
      `absolute -top-56 left-1/2 ${orbSize} -translate-x-1/2 rounded-full bg-[radial-gradient(circle,var(--dash-hero-orb),transparent)] blur-[210px]`
    )

    if (!isNarrow) {
      layers.push(
        prefersReducedMotion
          ? "absolute bottom-[-16rem] right-[10%] h-[28rem] w-[28rem] rounded-full bg-[radial-gradient(circle,var(--dash-hero-pulse),transparent)] opacity-70 blur-[180px]"
          : "absolute bottom-[-18rem] right-[8%] h-[34rem] w-[34rem] animate-[pulse_14s_ease-in-out_infinite] rounded-full bg-[radial-gradient(circle,var(--dash-hero-pulse),transparent)] blur-[210px]"
      )
    }

    if (!prefersReducedMotion && !isNarrow) {
      layers.push(
        "absolute -left-28 top-1/2 h-[30rem] w-[30rem] -translate-y-1/2 animate-[spin_26s_linear_infinite] rounded-full bg-(--grad-dash-conic) opacity-80 blur-[220px]"
      )
    } else if (!isNarrow) {
      layers.push(
        "absolute -left-24 top-1/2 h-[26rem] w-[26rem] -translate-y-1/2 rounded-full bg-(--grad-dash-conic-simple) opacity-60 blur-[200px]"
      )
    }

    return layers
  }, [isNarrow, prefersReducedMotion])

  const showHeaderMotion = !prefersReducedMotion && !isNarrow

  return (
    <section
      className={cn(
        "relative flex w-full flex-col overflow-hidden",
        "px-4 pb-16 pt-10 text-(--text-primary) sm:px-8 md:px-12 lg:px-16",
        "bg-linear-[145deg,var(--hero-grad-start),var(--hero-grad-end)]"
      )}
    >
      <div aria-hidden="true" className="pointer-events-none absolute inset-0">
        {heroBackdropLayers.map((layer, index) => (
          <div key={index} className={layer} />
        ))}
      </div>
      <div className="relative z-(--z-deep) space-y-6">
        <ScrollReveal mode="pop" delay={0.1} width="100%">
          <header
            className={cn(
              "group card-glass rounded-xl transition-all duration-500 ease-[cubic-bezier(0.34,1.56,0.64,1)]",
              "hover:-translate-y-1 hover:scale-[1.01] hover:shadow-xl motion-reduce:hover:transform-none motion-reduce:hover:shadow-none",
              "p-6 md:p-9 focus-within:shadow-focus focus-visible:outline-none focus-visible:shadow-focus",
              headerGradientClass
            )}
          >
            <span
              aria-hidden="true"
              className="pointer-events-none absolute inset-0 dash-highlight-veil bg-(--flare-primary) opacity-10 transition-opacity duration-700"
            />
            {showHeaderMotion ? (
              <span
                aria-hidden="true"
                className="pointer-events-none absolute -inset-y-24 -left-1/2 w-[170%] skew-x-[-18deg] bg-linear-to-r from-transparent via-white/55 to-transparent opacity-0 transition-all duration-2200 ease-out group-hover:translate-x-[35%] group-hover:opacity-70"
              >
                <span className="block h-full w-full animate-skeleton-wave bg-linear-to-r from-transparent via-white/70 to-transparent" />
              </span>
            ) : (
              <span
                aria-hidden="true"
                className="pointer-events-none absolute -inset-y-20 -left-1/2 w-[160%] skew-x-[-14deg] bg-linear-to-r from-transparent via-white/35 to-transparent opacity-0 transition-opacity duration-700 ease-out group-hover:opacity-45"
              />
            )}
            <div className="pointer-events-none absolute -right-24 top-1/2 h-64 w-64 -translate-y-1/2 rounded-full bg-(--flare-highlight) dash-highlight-veil blur-3xl" />
            {showHeaderMotion ? (
              <div className="pointer-events-none absolute left-[-20%] top-[-40%] h-56 w-56 animate-[spin_18s_linear_infinite] rounded-full bg-(--grad-dash-conic) opacity-60 blur-[120px]" />
            ) : (
              <div className="pointer-events-none absolute left-[-18%] top-[-42%] h-48 w-48 rounded-full bg-(--grad-dash-conic-simple) opacity-50 blur-[110px]" />
            )}
            <div className="relative grid gap-6 lg:grid-cols-12 lg:items-center">
              <div className="space-y-3 text-(--text-primary) lg:col-span-8">
                <h1 className="font-display text-(--fs-hero) font-extrabold leading-tight">
                  {greeting}
                  {user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""}!
                </h1>
                <div
                  className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-(--text-primary)/90"
                  role="status"
                  aria-live="polite"
                >
                  <Badge
                    size="sm"
                    className="shrink-0 border-glass-border-subtle bg-(--bg-surface-hover) font-mono text-base text-(--text-primary)/80 dark:text-(--text-primary)/80"
                    aria-label={t("common:ariaCurrentTime")}
                  >
                    <span className="flex items-baseline gap-1 font-mono text-lg leading-none">
                      <span>{hh}</span>
                      <span aria-hidden="true" className="inline-block animate-dash-colon-blink">
                        :
                      </span>
                      <span>{mm}</span>
                    </span>
                  </Badge>
                  <WeatherWidget className="shrink-0" />
                  <span className="text-sm font-medium tracking-tight leading-tight">
                    {dateStr}
                  </span>
                </div>
              </div>
              <div className="hidden justify-end md:flex lg:col-span-4">
                <Magnetic strength={0.25}>
                  <Button
                    variant="outline"
                    size="md"
                    className="whitespace-nowrap px-5 transition-transform duration-300 hover:-translate-y-[2px]"
                    onClick={() => navigate("/profile")}
                    aria-label={t("navigation:aria.openProfile")}
                  >
                    {t("navigation:menu.profile")}
                  </Button>
                </Magnetic>
              </div>
            </div>
          </header>
        </ScrollReveal>
      </div>
    </section>
  )
}





