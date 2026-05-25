import { m, AnimatePresence } from "framer-motion"
import useMediaQuery from "@/hooks/useMediaQuery"
import { useTranslation } from "react-i18next"
import { Info, Percent } from "lucide-react"
import { useQueryClient } from "@tanstack/react-query"
import api from "@/api/client"
// Wave 163 SW3 — TanStack Query factory for /admin/feature-flags.
// Closes W150 §Honesty #3 deferral.
import { updateFeatureFlagInCache, useAdminFeatureFlagsQuery } from "@/api/hooks/adminFeatureFlags"
import { SwitchControl, Chip } from "@/components/settings"
import type { FlagStatus } from "@/types/Admin"

/**
 * AdminFeatureFlagsFeature — Wave 164 SW2 orchestrator.
 *
 * Migrated from `pages/AdminFeatureFlags.tsx` (194 lines) to match the
 * features/activity/ pattern (W112 SW2). The page is now a thin
 * <Layout><FeatureErrorBoundary> wrapper; the feature owns content + state.
 *
 * Data layer: W163 SW3 TanStack Query factory at @/api/hooks/adminFeatureFlags
 * (useAdminFeatureFlagsQuery + updateFeatureFlagInCache cache mutation helper).
 * Closes W150 §Honesty #1 (features/admin/ structure migration).
 */
export function AdminFeatureFlagsFeature() {
  const queryClient = useQueryClient()
  // Wave 163 SW3 — useAdminFeatureFlagsQuery replaces pre-W163 useCallback
  // fetchFlags + useState + useEffect. Loading state derived from isPending.
  const { data: flags = [], isPending: loading } = useAdminFeatureFlagsQuery()
  const { t } = useTranslation("admin")
  const reducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")

  const handleToggle = async (name: string, currentStatus: FlagStatus) => {
    const nextStatus: FlagStatus = currentStatus === "disabled" ? "enabled" : "disabled"
    await api.patch(`/admin/feature-flags/${name}`, { status: nextStatus })
    updateFeatureFlagInCache(queryClient, name, { status: nextStatus })
  }

  const handlePercentageChange = async (name: string, value: number) => {
    await api.patch(`/admin/feature-flags/${name}`, {
      status: "percentage",
      percentage: value,
    })
    updateFeatureFlagInCache(queryClient, name, { status: "percentage", percentage: value })
  }

  const getStatusColor = (status: FlagStatus) => {
    switch (status) {
      case "enabled":
        return "success"
      case "percentage":
        return "info"
      default:
        return "default"
    }
  }

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
                    {t("featureFlags.table.status")}
                  </th>
                  <th
                    scope="col"
                    className="px-6 py-4 text-xs font-bold uppercase tracking-wider text-(--text-secondary) opacity-medium"
                  >
                    {t("featureFlags.table.rollout")}
                  </th>
                  <th
                    scope="col"
                    className="px-6 py-4 text-right text-xs font-bold uppercase tracking-wider text-(--text-secondary) opacity-strong"
                  >
                    {t("featureFlags.table.details")}
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
                        <div className="flex items-center gap-4">
                          <Chip
                            label={flag.status.toUpperCase()}
                            color={
                              getStatusColor(flag.status) === "success"
                                ? "success"
                                : getStatusColor(flag.status) === "info"
                                  ? "primary"
                                  : "default"
                            }
                            className="w-24 justify-center"
                          />
                          <SwitchControl
                            checked={flag.status !== "disabled"}
                            onChange={() => handleToggle(flag.name, flag.status)}
                          />
                        </div>
                      </td>
                      <td className="px-6 py-5">
                        {flag.status === "percentage" ? (
                          <div className="flex flex-col gap-2 min-w-(--min-w-column)">
                            <input
                              type="range"
                              min="0"
                              max="100"
                              step="5"
                              value={flag.percentage}
                              aria-label={t("featureFlags.rollout.range")}
                              onChange={(event) =>
                                handlePercentageChange(flag.name, parseInt(event.target.value))
                              }
                              className="h-1.5 w-full cursor-pointer appearance-none rounded-lg bg-glass-border accent-brand"
                            />
                            <div className="flex items-center justify-between text-label-xs font-bold uppercase tracking-widest text-(--text-secondary)">
                              <span>
                                {t("featureFlags.rollout.percentage", { value: flag.percentage })}
                              </span>
                              <Percent className="h-3 w-3" />
                            </div>
                          </div>
                        ) : (
                          <span className="text-sm italic text-(--text-secondary) opacity-medium">
                            {t("featureFlags.rollout.global")}
                          </span>
                        )}
                      </td>
                      <td className="px-6 py-5 text-right">
                        <button
                          type="button"
                          title={JSON.stringify(flag.metadata, null, 2)}
                          aria-label={t("featureFlags.actions.viewMetadata")}
                          className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg text-(--text-secondary) transition-colors hover:bg-(--bg-surface-hover)/(--opacity-dim) hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2"
                        >
                          <Info className="h-4 w-4" aria-hidden="true" />
                        </button>
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
