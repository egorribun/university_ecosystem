import { useRouterState } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { SEO } from "@/components/ui/SEO"

const PAGE_TITLE_KEYS = {
  "/_public/login": "auth:login.title",
  "/_public/forgot-password": "auth:forgot.title",
  "/_public/register": "auth:register.title",
  "/_public/reset-password": "auth:reset.title",
  "/_public/reset-password/$token": "auth:reset.title",
  "/_auth/settings": "settings:page.title",
  "/_auth/map": "system:map.title",
  "/_auth/messenger": "messenger:title",
  "/_auth/messenger/$chatId": "messenger:title",
} as const

const EXISTING_PAGE_SEO_ROUTE_IDS = [
  "/_auth/activity",
  "/_auth/dashboard",
  "/_auth/events/",
  "/_auth/events/$id",
  "/_auth/news/",
  "/_auth/news/$id",
  "/_auth/profile",
  "/_auth/schedule",
]

export const PAGE_SEO_ROUTE_IDS: ReadonlySet<string> = new Set([
  ...EXISTING_PAGE_SEO_ROUTE_IDS,
  ...Object.keys(PAGE_TITLE_KEYS),
])

export function PageRouteSEO() {
  const routeId = useRouterState({
    // Root fallback metadata is suppressed for successful page-SEO matches.
    // A failed leaf may still have a successful mapped parent (e.g. a reset
    // token route), so choose the deepest successful mapped match.
    select: (state) =>
      state.matches
        .slice()
        .reverse()
        .find((match) => match.status === "success" && match.routeId.toString() in PAGE_TITLE_KEYS)
        ?.routeId.toString(),
  })
  const { t } = useTranslation(["auth", "settings", "system", "messenger"])
  const titleKey = routeId ? PAGE_TITLE_KEYS[routeId as keyof typeof PAGE_TITLE_KEYS] : undefined

  if (!titleKey) return null

  return <SEO title={t(titleKey)} />
}
