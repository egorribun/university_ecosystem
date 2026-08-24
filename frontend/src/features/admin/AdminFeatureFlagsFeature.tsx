import { m, AnimatePresence } from "framer-motion"
import useMediaQuery from "@/hooks/useMediaQuery"
import { useTranslation } from "react-i18next"
import { Info } from "lucide-react"
import { useAdminFeatureFlagsQuery } from "@/api/hooks/adminFeatureFlags"
import { Chip } from "@/components/settings"

/**
 * AdminFeatureFlagsFeature — Wave 164 SW2 orchestrator.
 *
 * Migrated from `pages/AdminFeatureFlags.tsx` (194 lines) to match the
 * features/activity/ pattern (W112 SW2). The page is now a thin
 * <Layout><FeatureErrorBoundary> wrapper; the feature owns content + state.
 *
 * This is deliberately a read-only diagnostics surface. Configuration is
 * version-controlled and promoted by GitOps so the UI cannot imply a write
 * succeeded when flagd's ConfigMap was never changed.
 */
export function AdminFeatureFlagsFeature() {
  const { data: flags = [], isPending: loading } = useAdminFeatureFlagsQuery()
  const { t } = useTranslation("admin")
  const reducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background/(--opacity-medium)">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-brand border-t-transparent" />
      </div>
    )
  }

  return (
    <div className="min-h-screen w-full bg-background/(--opacity-medium) py-12">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <m.div
          initial={reducedMotion ? false : { opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={reducedMotion ? { duration: 0 } : { duration: 0.5 }}
          className="mb-8"
        >
          <h1 className="text-4xl font-bold tracking-tight text-(--text-primary) sm:text-5xl">
            {t("featureFlags.title")}
          </h1>
          <p className="mt-2 text-base text-(--text-secondary)">{t("featureFlags.subtitle")}</p>
        </m.div>

        <div
          role="note"
          className="mb-6 flex items-start gap-3 rounded-lg border border-brand/(--opacity-medium) bg-brand/(--opacity-subtle) p-4 text-sm text-(--text-primary)"
        >
          <Info className="mt-0.5 h-5 w-5 shrink-0 text-brand" aria-hidden="true" />
          <p>{t("featureFlags.management.notice")}</p>
        </div>

        <div className="overflow-hidden rounded-lg border border-glass-border bg-(--bg-surface)/(--opacity-medium) shadow-glass">
          <div className="overflow-x-auto">
            <table
              className="w-full text-left border-collapse"
              aria-label={t("featureFlags.table.aria")}
            >
              <thead>
                <tr className="border-b border-glass-border/(--opacity-subtle) bg-(--bg-surface-hover)/(--opacity-dim)">
                  <th
                    scope="col"
                    className="px-6 py-4 text-xs font-bold uppercase tracking-wider text-(--text-secondary) opacity-medium"
                  >
                    {t("featureFlags.table.flag")}
                  </th>
                  <th
                    scope="col"
                    className="px-6 py-4 text-xs font-bold uppercase tracking-wider text-(--text-secondary) opacity-medium"
                  >
                    {t("featureFlags.table.effective")}
                  </th>
                  <th
                    scope="col"
                    className="px-6 py-4 text-xs font-bold uppercase tracking-wider text-(--text-secondary) opacity-medium"
                  >
                    {t("featureFlags.table.fallback")}
                  </th>
                  <th
                    scope="col"
                    className="px-6 py-4 text-right text-xs font-bold uppercase tracking-wider text-(--text-secondary) opacity-strong"
                  >
                    {t("featureFlags.table.management")}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-glass-border/(--opacity-subtle)">
                <AnimatePresence mode="popLayout">
                  {flags.map((flag, index) => (
                    <m.tr
                      key={flag.name}
                      initial={reducedMotion ? false : { opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={reducedMotion ? { duration: 0 } : { delay: index * 0.05 }}
                      className="transition-colors hover:bg-(--bg-surface-hover)/(--opacity-subtle)"
                    >
                      <td className="px-6 py-5">
                        <div className="flex flex-col gap-1">
                          <span className="text-base font-bold text-text-primary">{flag.name}</span>
                          <span className="text-xs text-(--text-secondary) max-w-xs opacity-strong">
                            {flag.description}
                          </span>
                        </div>
                      </td>
                      <td className="px-6 py-5">
                        <Chip
                          label={
                            flag.enabled
                              ? t("featureFlags.values.on")
                              : t("featureFlags.values.off")
                          }
                          color={flag.enabled ? "success" : "default"}
                          className="w-24 justify-center"
                        />
                      </td>
                      <td className="px-6 py-5">
                        <span className="text-sm font-medium text-(--text-secondary)">
                          {flag.default
                            ? t("featureFlags.values.on")
                            : t("featureFlags.values.off")}
                        </span>
                      </td>
                      <td className="px-6 py-5 text-right text-xs text-(--text-secondary)">
                        <div className="flex flex-col items-end gap-1">
                          <span className="font-semibold text-(--text-primary)">
                            {flag.provider}
                          </span>
                          <span>{flag.evaluation_reason}</span>
                          <code className="rounded bg-(--bg-surface-hover) px-2 py-1">
                            {flag.config_path}
                          </code>
                        </div>
                      </td>
                    </m.tr>
                  ))}
                </AnimatePresence>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}
