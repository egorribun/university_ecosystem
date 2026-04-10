import { Link } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"

interface NewsDetailNavigationProps {
  prevId: string | null
  nextId: string | null
  prevTitle: string | null
  nextTitle: string | null
}

export function NewsDetailNavigation({
  prevId,
  nextId,
  prevTitle,
  nextTitle,
}: NewsDetailNavigationProps) {
  const { t } = useTranslation(["news"])

  if (!prevId && !nextId) return null

  return (
    <nav
      className="flex items-stretch gap-4 border-t border-glass-border/(--opacity-soft) pt-6"
      aria-label={t("news:navigation.label")}
    >
      {prevId ? (
        <Link
          to="/news/$id"
          params={{ id: prevId }}
          className="group flex flex-1 flex-col gap-1 rounded-xl glass-layer-surface border border-glass-border/(--opacity-soft) p-4 transition hover:shadow-glass hover:-translate-y-0.5"
        >
          <span className="text-[10px] font-semibold uppercase tracking-wider text-(--text-secondary)">
            {t("news:navigation.prev")}
          </span>
          <span className="text-sm font-semibold text-text-primary line-clamp-1 group-hover:text-brand transition-colors">
            {prevTitle}
          </span>
        </Link>
      ) : (
        <div className="flex-1" />
      )}

      {nextId ? (
        <Link
          to="/news/$id"
          params={{ id: nextId }}
          className="group flex flex-1 flex-col gap-1 rounded-xl glass-layer-surface border border-glass-border/(--opacity-soft) p-4 text-right transition hover:shadow-glass hover:-translate-y-0.5"
        >
          <span className="text-[10px] font-semibold uppercase tracking-wider text-(--text-secondary)">
            {t("news:navigation.next")}
          </span>
          <span className="text-sm font-semibold text-text-primary line-clamp-1 group-hover:text-brand transition-colors">
            {nextTitle}
          </span>
        </Link>
      ) : (
        <div className="flex-1" />
      )}
    </nav>
  )
}
