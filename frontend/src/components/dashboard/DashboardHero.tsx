import type { User } from "@/types/User"
// useNavigate removed — profile button removed (accessible via navbar)
import { useTranslation } from "react-i18next"
import { useMemo } from "react"
import { motion } from "framer-motion"
import { Badge } from "@/components/ui"
import WeatherWidget from "@/components/ui/WeatherWidget"
import { ScrollReveal } from "@/components/motion/ScrollReveal"
import { cn } from "@/utils/cn"
import { Sparkles } from "lucide-react"
import { useGreeting, type GreetingKey } from "@/hooks/useGreeting"

/** Wave 48: Day progress ring gradient colors per greeting palette */
const RING_COLORS: Record<GreetingKey, [string, string]> = {
  morning: ["#f59e0b", "#fbbf24"],   // amber
  afternoon: ["#38bdf8", "#0ea5e9"], // sky
  evening: ["#8b5cf6", "#a78bfa"],   // violet
  night: ["#64748b", "#94a3b8"],     // slate
}

/** SVG ring constants */
const RING_SIZE = 22
const RING_STROKE = 2.5
const RING_RADIUS = (RING_SIZE - RING_STROKE) / 2
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS

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
  const { greeting, greetingKey, specialKey, emoji } = useGreeting(time)

  // Wave 48: Day progress (0% at 00:00 → 100% at 23:59)
  const dayProgress = useMemo(() => {
    const totalMinutes = time.getHours() * 60 + time.getMinutes()
    return totalMinutes / 1440 // 24*60
  }, [time])
  const ringOffset = RING_CIRCUMFERENCE * (1 - dayProgress)
  const [ringColor1, ringColor2] = RING_COLORS[greetingKey]

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
              "px-8 py-8 md:px-10 md:py-9",
              `greeting-${greetingKey}`
            )}
            style={{
              background: "var(--hero-card-bg)",
              /* Wave 47: ambient glow — colored outer shadow from greeting palette */
              boxShadow: "0 1px 3px color-mix(in srgb, black 8%, transparent), 0 4px 16px color-mix(in srgb, black 6%, transparent), inset 0 1px 0 color-mix(in srgb, white 4%, transparent), 0 8px 48px color-mix(in srgb, var(--hero-grad-start) 18%, transparent)",
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
                  {/* Wave 47: Sparkle icon on special days */}
                  {specialKey && (
                    <motion.span
                      initial={{ opacity: 0, scale: 0 }}
                      animate={{ opacity: 1, scale: 1 }}
                      transition={{ type: "spring", stiffness: 400, damping: 15, delay: 0.3 }}
                      className="mr-2 inline-flex text-amber-400"
                    >
                      <Sparkles className="h-8 w-8" aria-hidden="true" />
                    </motion.span>
                  )}
                  {greeting}
                  {user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""}!
                  {/* Wave 48: Contextual emoji */}
                  {emoji && (
                    <motion.span
                      initial={{ opacity: 0, scale: 0.5 }}
                      animate={{ opacity: 1, scale: 1 }}
                      transition={{ type: "spring", stiffness: 400, damping: 15, delay: 0.5 }}
                      className="ml-2 inline-block"
                      aria-hidden="true"
                    >
                      {emoji}
                    </motion.span>
                  )}
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
                  {/* Wave 48: Day progress ring — replaces time-of-day icon */}
                  <motion.span
                    className="inline-flex items-center shrink-0"
                    initial={{ opacity: 0, scale: 0.5 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ type: "spring", stiffness: 300, damping: 20 }}
                    aria-label={t("common:ariaDayProgress", { defaultValue: `${Math.round(dayProgress * 100)}% of day` })}
                  >
                    <svg
                      width={RING_SIZE}
                      height={RING_SIZE}
                      viewBox={`0 0 ${RING_SIZE} ${RING_SIZE}`}
                      className="block -rotate-90"
                      aria-hidden="true"
                    >
                      <defs>
                        <linearGradient id="day-ring-grad" x1="0%" y1="0%" x2="100%" y2="0%">
                          <stop offset="0%" stopColor={ringColor1} />
                          <stop offset="100%" stopColor={ringColor2} />
                        </linearGradient>
                      </defs>
                      {/* Track */}
                      <circle
                        cx={RING_SIZE / 2}
                        cy={RING_SIZE / 2}
                        r={RING_RADIUS}
                        fill="none"
                        stroke="currentColor"
                        strokeWidth={RING_STROKE}
                        className="text-(--text-tertiary) opacity-dim"
                      />
                      {/* Progress arc */}
                      <circle
                        cx={RING_SIZE / 2}
                        cy={RING_SIZE / 2}
                        r={RING_RADIUS}
                        fill="none"
                        stroke="url(#day-ring-grad)"
                        strokeWidth={RING_STROKE}
                        strokeLinecap="round"
                        strokeDasharray={RING_CIRCUMFERENCE}
                        strokeDashoffset={ringOffset}
                        className="transition-all duration-slow"
                      />
                    </svg>
                  </motion.span>
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
