import { type ReactNode } from "react"
import type { User } from "@/types/User"
import { useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Badge, Button } from "@/components/ui"
import WeatherWidget from "@/components/WeatherWidget"
import Magnetic from "@/components/Magnetic"
import { ScrollReveal } from "@/components/ScrollReveal"
import { cn } from "@/utils/cn"
import { useGreeting } from "@/hooks/useGreeting"
import { DashboardBackdrop } from "./DashboardBackdrop"

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

export function DashboardHero({
  user,
  time,
  hh,
  mm,
  dateStr,
  isNarrow,
  prefersReducedMotion,
  children,
}: DashboardHeroProps) {
  const navigate = useNavigate()
  const { t } = useTranslation(["dashboard", "common", "navigation"])
  const { greeting } = useGreeting(time)

  const headerGradientClass = cn(
    "transition-[background] duration-slower",
    isNarrow ? "bg-(--grad-header-135)" : "bg-(--grad-header-125)"
  )

  const showHeaderMotion = !prefersReducedMotion && !isNarrow

  return (
    <section
      className={cn(
        "relative flex w-full flex-col overflow-hidden",
        "px-4 pb-16 pt-10 text-text-primary sm:px-8 md:px-12 lg:px-16",
        "bg-linear-[145deg,var(--hero-grad-start),var(--hero-grad-end)]"
      )}
    >
      <DashboardBackdrop isNarrow={isNarrow} prefersReducedMotion={prefersReducedMotion} />

      <div className="relative z-deep space-y-6">
        <ScrollReveal mode="pop" delay={0.1} width="100%">
          <header
            className={cn(
              "group card-glass rounded-sm transition-all duration-slow ease-[cubic-bezier(0.34,1.56,0.64,1)]",
              "hover:-translate-y-1 hover:scale-[1.01] hover:shadow-xl motion-reduce:hover:transform-none motion-reduce:hover:shadow-none",
              "p-6 md:p-9 focus-within:shadow-focus focus-ring-premium",
              headerGradientClass
            )}
          >
            <span
              aria-hidden="true"
              className="pointer-events-none absolute inset-0 dash-highlight-veil bg-(--flare-primary) opacity-subtle transition-opacity duration-slower"
            />
            {showHeaderMotion ? (
              <span
                aria-hidden="true"
                className="pointer-events-none absolute -inset-y-24 -left-1 w-[170%] skew-x-[-18deg] bg-linear-to-r from-transparent via-white/(--opacity-medium) to-transparent opacity-0 transition-all duration-slower ease-out group-hover:translate-x-[35%] group-hover:opacity-strong"
              >
                <span className="block h-full w-full animate-skeleton-wave bg-linear-to-r from-transparent via-white/(--opacity-strong) to-transparent" />
              </span>
            ) : (
              <span
                aria-hidden="true"
                className="pointer-events-none absolute -inset-y-20 -left-1 w-[160%] skew-x-[-14deg] bg-linear-to-r from-transparent via-white/(--opacity-soft) to-transparent opacity-0 transition-opacity duration-slower ease-out group-hover:opacity-medium"
              />
            )}
            <div className="pointer-events-none absolute -right-24 top-1 h-64 w-64 -translate-y-1/2 rounded-full bg-(--flare-highlight) dash-highlight-veil blur-3xl" />
            {showHeaderMotion ? (
              <div className="pointer-events-none absolute left-[-20%] top-[-40%] h-[14rem] w-[14rem] animate-[spin_18s_linear_infinite] rounded-full bg-(--grad-dash-conic) opacity-strong blur-(--glow-blur-lg)" />
            ) : (
              <div className="pointer-events-none absolute left-[-18%] top-[-42%] h-[12rem] w-[12rem] rounded-full bg-(--grad-dash-conic-simple) opacity-medium blur-(--glow-blur-md)" />
            )}
            <div className="relative grid gap-6 lg:grid-cols-12 lg:items-center">
              <div className="space-y-3 text-text-primary lg:col-span-8">
                <h1 className="font-display text-(--fs-hero) font-extrabold leading-tight">
                  {greeting}
                  {user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""}!
                </h1>
                <div
                  className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-text-primary/(--opacity-heavy)"
                  role="status"
                  aria-live="polite"
                >
                  <Badge
                    size="sm"
                    className="shrink-0 border-glass-border-subtle bg-(--bg-surface-hover) font-mono text-base text-text-primary/(--opacity-hover) dark:text-text-primary/(--opacity-hover)"
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
                    className="whitespace-nowrap px-5 transition-transform duration-base hover:-translate-y-[0.125rem]"
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

      {children && (
        <div className="relative z-base -mt-10 px-4 sm:px-8 md:px-12 lg:px-16">{children}</div>
      )}
    </section>
  )
}
