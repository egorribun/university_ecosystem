import { useCallback, useEffect, useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { useTranslation } from "react-i18next"
import { Info, Percent } from "lucide-react"
import api from "@/api/client"
import Layout from "@/components/Layout"
import { SwitchControl, Chip } from "@/components/settings"
import { FeatureFlag, FlagStatus } from "@/types/Admin"

export default function AdminFeatureFlags() {
  const [flags, setFlags] = useState<FeatureFlag[]>([])
  const [loading, setLoading] = useState(true)
  const { t } = useTranslation("admin")

  const fetchFlags = useCallback(async () => {
    try {
      const response = await api.get<FeatureFlag[]>("/admin/feature-flags")
      setFlags(response.data)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchFlags()
  }, [fetchFlags])

  const handleToggle = async (name: string, currentStatus: FlagStatus) => {
    const nextStatus: FlagStatus = currentStatus === "disabled" ? "enabled" : "disabled"
    await api.patch(`/admin/feature-flags/${name}`, { status: nextStatus })
    void fetchFlags()
  }

  const handlePercentageChange = async (name: string, value: number) => {
    await api.patch(`/admin/feature-flags/${name}`, {
      status: "percentage",
      percentage: value,
    })
    void fetchFlags()
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
      <Layout>
        <div className="flex min-h-screen items-center justify-center bg-background/(--opacity-medium)">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-brand border-t-transparent" />
        </div>
      </Layout>
    )
  }

  return (
    <Layout>
      <div className="min-h-screen w-full bg-background/(--opacity-medium) py-12">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="mb-8"
          >
<<<<<<< HEAD
            <h1 className="text-4xl font-bold tracking-tight text-(--text-primary) sm:text-5xl">
              {t("featureFlags.title")}
=======
            <h1 className="text-4xl font-bold tracking-tight text-text-primary sm:text-5xl">
              {t("featureFlags.title", "Dynamic Feature Flags")}
>>>>>>> origin/main
            </h1>
            <p className="mt-2 text-base text-(--text-secondary)">
              {t("featureFlags.subtitle")}
            </p>
          </motion.div>

          <div className="overflow-hidden rounded-lg border border-glass-border bg-(--bg-surface)/(--opacity-medium) shadow-glass">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-glass-border/(--opacity-subtle) bg-(--bg-surface-hover)/(--opacity-dim)">
                    <th className="px-6 py-4 text-xs font-bold uppercase tracking-wider text-(--text-secondary) opacity-medium">
                      {t("featureFlags.table.flag", "Feature Flag")}
                    </th>
                    <th className="px-6 py-4 text-xs font-bold uppercase tracking-wider text-(--text-secondary) opacity-medium">
                      {t("featureFlags.table.status", "Status")}
                    </th>
                    <th className="px-6 py-4 text-xs font-bold uppercase tracking-wider text-(--text-secondary) opacity-medium">
                      {t("featureFlags.table.rollout", "Rollout")}
                    </th>
                    <th className="px-6 py-4 text-right text-xs font-bold uppercase tracking-wider text-(--text-secondary) opacity-strong">
                      {t("featureFlags.table.details", "Details")}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-glass-border/(--opacity-subtle)">
                  <AnimatePresence mode="popLayout">
                    {flags.map((flag, index) => (
                      <motion.tr
                        key={flag.name}
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: index * 0.05 }}
                        className="transition-colors hover:bg-(--bg-surface-hover)/(--opacity-subtle)"
                      >
                        <td className="px-6 py-5">
                          <div className="flex flex-col gap-1">
                            <span className="text-base font-bold text-text-primary">
                              {flag.name}
                            </span>
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
                                aria-label={t("featureFlags.rollout.range", "Rollout Percentage")}
                                onChange={(event) =>
                                  handlePercentageChange(flag.name, parseInt(event.target.value))
                                }
                                className="h-1.5 w-full cursor-pointer appearance-none rounded-lg bg-glass-border accent-brand"
                              />
                              <div className="flex items-center justify-between text-label-xs font-bold uppercase tracking-widest text-(--text-secondary)">
                                <span>{t("featureFlags.rollout.percentage", { value: flag.percentage })}</span>
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
                            title={JSON.stringify(flag.metadata, null, 2)}
                            className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-(--text-secondary) transition-colors hover:bg-(--bg-surface-hover)/(--opacity-dim) hover:text-brand"
                          >
                            <Info className="h-4 w-4" />
                          </button>
                        </td>
                      </motion.tr>
                    ))}
                  </AnimatePresence>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </Layout>
  )
}
