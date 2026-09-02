import { useTranslation } from "react-i18next"
import { Calendar, MessageCircle, Newspaper, Zap, Sparkles } from "lucide-react"

import { FadeIn } from "@/components/ui/motion/FadeIn"
import { motion } from "@/theme/tokens"

export function LoginHero() {
  const { t } = useTranslation("auth")

  const heroHighlights = [
    {
      icon: Calendar,
      title: t("login.highlightSchedule"),
      description: t("login.highlightScheduleDescription"),
    },
    {
      icon: Newspaper,
      title: t("login.highlightNews"),
      description: t("login.highlightNewsDescription"),
    },
    {
      icon: MessageCircle,
      title: t("login.highlightMessenger"),
      description: t("login.highlightMessengerDescription"),
    },
  ]

  return (
    <FadeIn
      direction="left"
      distance={200}
      duration={motion.durationSlow}
      className="auth-card-glass flex w-full min-w-0 flex-col justify-center p-8 lg:p-12"
    >
      <p className="text-sm font-semibold uppercase tracking-hero text-text-primary/(--opacity-strong)">
        {t("login.heroBadge")}
      </p>
      <h1 className="mt-4 text-4xl font-extrabold leading-tight text-text-primary sm:text-5xl">
        {t("login.heroHeading")}
      </h1>
      <p className="mt-4 text-lg leading-relaxed text-text-secondary">
        {t("login.heroDescription")}
      </p>

      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        {heroHighlights.map(({ icon: Icon, title, description }) => (
          <div key={title} className="auth-perk-card group">
            <div className="relative z-base flex items-center gap-3">
              <span className="flex size-12 items-center justify-center rounded-md bg-brand-subtle-bg text-brand">
                <Icon className="h-5 w-5" aria-hidden="true" />
              </span>
              <p className="text-base font-semibold">{title}</p>
            </div>
            <p className="mt-4 text-sm text-text-secondary">{description}</p>
          </div>
        ))}
      </div>

      <div className="mt-10 flex flex-wrap gap-4">
        <div className="auth-stat-glass w-auto px-6">
          <Zap className="mr-1 h-4 w-4 text-brand" strokeWidth={3} />
          <span className="text-xs font-extrabold uppercase tracking-widest-xl">
            {t("login.statFast")}
          </span>
          <span className="text-xs font-extrabold uppercase tracking-widest-xl ml-1">
            {t("login.statFastLabel")}
          </span>
        </div>
        <div className="auth-stat-glass w-auto px-6">
          <Sparkles className="mr-1 h-4 w-4 text-brand" strokeWidth={3} />
          <span className="text-xs font-extrabold uppercase tracking-widest-xl">
            {t("login.statSmart")}
          </span>
        </div>
      </div>
    </FadeIn>
  )
}
