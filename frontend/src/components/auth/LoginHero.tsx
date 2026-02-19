import { useTranslation } from "react-i18next"
import { Calendar, MessageCircle, Newspaper, Zap, Sparkles } from "lucide-react"

import { FadeIn } from "@/components/ui/motion/FadeIn"
import { motion } from "@/theme/tokens"

export function LoginHero() {
  const { t } = useTranslation(["auth"])

  const heroHighlights = [
    {
      icon: Calendar,
      title: t("auth:login.highlightSchedule", {
        defaultValue: "Расписание занятий",
      }),
      description: t("auth:login.highlightScheduleDescription", {
        defaultValue: "Актуальное расписание пар, экзаменов и консультаций.",
      }),
    },
    {
      icon: Newspaper,
      title: t("auth:login.highlightNews", {
        defaultValue: "Новости и мероприятия",
      }),
      description: t("auth:login.highlightNewsDescription", {
        defaultValue: "Будьте в курсе университетской жизни и важных событий.",
      }),
    },
    {
      icon: MessageCircle,
      title: t("auth:login.highlightMessenger", {
        defaultValue: "Мессенджер",
      }),
      description: t("auth:login.highlightMessengerDescription", {
        defaultValue: "Общайтесь с одногруппниками и преподавателями.",
      }),
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
        {t("auth:login.heroBadge", { defaultValue: "University Ecosystem" })}
      </p>
      <h1 className="mt-4 text-4xl font-extrabold leading-tight text-text-primary sm:text-5xl">
        {t("auth:login.heroHeading", {
          defaultValue: "Добро пожаловать в систему Университета",
        })}
      </h1>
      <p className="mt-4 text-lg leading-relaxed text-text-secondary">
        {t("auth:login.heroDescription", {
          defaultValue:
            "Расписание, новости, мероприятия и мессенджер — всё в одном месте для студентов и преподавателей.",
        })}
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
            {t("auth:login.statFast", { defaultValue: "Быстро" })}
          </span>
          <span className="text-xs font-extrabold uppercase tracking-widest-xl ml-1">
            {t("auth:login.statFastLabel", { defaultValue: "и безопасно" })}
          </span>
        </div>
        <div className="auth-stat-glass w-auto px-6">
          <Sparkles className="mr-1 h-4 w-4 text-brand" strokeWidth={3} />
          <span className="text-xs font-extrabold uppercase tracking-widest-xl">
            {t("auth:login.statSmart", { defaultValue: "Умный интерфейс" })}
          </span>
        </div>
      </div>
    </FadeIn>
  )
}
