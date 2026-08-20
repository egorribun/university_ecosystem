import { memo, useEffect, useState } from "react"
import { m, AnimatePresence } from "framer-motion"
import useMediaQuery from "@/hooks/useMediaQuery"
import { useTranslation } from "react-i18next"
import { formatDate, presets } from "@/utils/date"
import {
  ChevronDown,
  ChevronUp,
  ShieldCheck,
  ShieldAlert,
  Info,
  Terminal,
  User,
  Activity,
} from "lucide-react"
import { useAdminAuditLogsQuery } from "@/api/hooks/adminAudit"
import { cn } from "@/utils/cn"
import { SectionCard, TextField, Button } from "@/components/settings"
import { AuditLog } from "@/types/Admin"
import { useDebounced } from "@/hooks/useDebounced"

const Row = memo(function Row({ log }: { log: AuditLog }) {
  const [open, setOpen] = useState(false)
  const { t } = useTranslation("admin")
  const reducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")

  const getActionColor = (action: string) => {
    if (action.includes("delete"))
      return "text-error bg-error/(--opacity-subtle) border-error/(--opacity-dim)"
    if (action.includes("create") || action.includes("add"))
      return "text-brand bg-brand/(--opacity-subtle) border-brand/(--opacity-dim)"
    if (action.includes("update") || action.includes("modify"))
      return "text-warning bg-warning/(--opacity-subtle) border-warning/(--opacity-dim)"
    return "text-(--text-secondary) bg-(--bg-surface-hover)/(--opacity-dim) border-glass-border/(--opacity-subtle)"
  }

  return (
    <>
      <tr
        className={cn(
          "transition-colors group",
          log.is_valid
            ? "hover:bg-(--bg-surface-hover)/(--opacity-subtle)"
            : "bg-error/(--opacity-subtle) hover:bg-error/(--opacity-subtle)",
          open && "bg-(--bg-surface-hover)/(--opacity-subtle)"
        )}
      >
        <td className="px-4 py-4">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setOpen(!open)}
            aria-expanded={open}
            aria-label={t("audit.table.toggleDetails", { id: log.id })}
            className="p-1 min-h-[44px] min-w-[44px] flex items-center justify-center text-(--text-secondary) hover:text-text-primary"
          >
            {open ? (
              <ChevronUp className="h-4 w-4" aria-hidden="true" />
            ) : (
              <ChevronDown className="h-4 w-4" aria-hidden="true" />
            )}
          </Button>
        </td>
        <td className="px-4 py-4">
          <div className="flex flex-col">
            <span className="text-sm font-bold text-text-primary">
              {formatDate(log.created_at, presets.auditDate)}
            </span>
            <span className="text-xs text-(--text-secondary) opacity-strong">
              {formatDate(log.created_at, presets.auditTime)}
            </span>
          </div>
        </td>
        <td className="px-4 py-4">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-brand/(--opacity-subtle) text-brand">
              <User className="h-4 w-4" aria-hidden="true" />
            </div>
            <div className="flex flex-col min-w-0">
              <span className="truncate text-sm font-bold text-text-primary">
                {log.actor_name || t("audit.details.system")}
              </span>
              <span className="truncate text-label-xs uppercase tracking-wider text-(--text-secondary) opacity-medium">
                {log.actor_user_id || "SYSTEM"}
              </span>
            </div>
          </div>
        </td>
        <td className="px-4 py-4">
          <span
            className={cn(
              "inline-flex items-center rounded-lg border px-2 py-0.5 text-micro font-bold uppercase tracking-wider",
              getActionColor(log.action)
            )}
          >
            {log.action.replace(/\./g, " ").toUpperCase()}
          </span>
        </td>
        <td className="px-4 py-4">
          <div className="flex items-center gap-1.5 text-sm text-(--text-secondary)">
            <Activity className="h-3.5 w-3.5 opacity-medium" aria-hidden="true" />
            <span>{log.resource_type}</span>
          </div>
        </td>
        <td className="px-4 py-4 text-center">
          <div className="flex justify-center">
            {log.is_valid ? (
              <div
                className="flex h-6 w-6 items-center justify-center rounded-full bg-brand/(--opacity-subtle) text-brand"
                title={t("audit.details.integrityVerified")}
              >
                <ShieldCheck className="h-4 w-4" aria-hidden="true" />
              </div>
            ) : (
              <div
                className="flex h-6 w-6 items-center justify-center rounded-full bg-error/(--opacity-subtle) text-error"
                title={t("audit.details.integrityTampered")}
              >
                <ShieldAlert className="h-4 w-4" aria-hidden="true" />
              </div>
            )}
          </div>
        </td>
      </tr>
      <AnimatePresence>
        {open && (
          <tr>
            <td colSpan={6} className="p-0 border-none">
              <m.div
                initial={reducedMotion ? false : { height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={reducedMotion ? { opacity: 0 } : { height: 0, opacity: 0 }}
                transition={reducedMotion ? { duration: 0 } : { duration: 0.2 }}
                className="overflow-hidden"
              >
                <div className="mx-4 mb-4 mt-2 rounded-md border border-glass-border bg-(--bg-surface)/(--opacity-medium) p-6 shadow-sm">
                  <div className="mb-4 flex items-center gap-2 text-sm font-bold text-text-primary">
                    <Info className="h-4 w-4 text-brand" aria-hidden="true" />
                    <span>{t("audit.details.title")}</span>
                  </div>

                  <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
                    <div className="space-y-1">
                      <span className="text-label-xs font-bold uppercase tracking-widest text-(--text-secondary) opacity-medium">
                        {t("audit.details.resourceId")}
                      </span>
                      <p className="text-sm font-mono text-text-primary select-all">
                        {log.resource_id || t("audit.details.notAvailable")}
                      </p>
                    </div>
                    <div className="space-y-1">
                      <span className="text-label-xs font-bold uppercase tracking-widest text-(--text-secondary) opacity-medium">
                        {t("audit.details.subject")}
                      </span>
                      <p className="text-sm text-text-primary">
                        {log.subject_name || t("audit.details.notAvailable")}
                        <span className="ml-1 text-xs opacity-medium">
                          ({log.subject_user_id || t("audit.details.notAvailable")})
                        </span>
                      </p>
                    </div>
                    <div className="space-y-1">
                      <span className="text-label-xs font-bold uppercase tracking-widest text-(--text-secondary) opacity-medium">
                        {t("audit.details.ipAddress")}
                      </span>
                      <p className="text-sm font-mono text-text-primary">
                        {log.ip_address || t("audit.details.unknown")}
                      </p>
                    </div>
                    <div className="space-y-1">
                      <span className="text-label-xs font-bold uppercase tracking-widest text-(--text-secondary) opacity-medium">
                        {t("audit.details.userAgent")}
                      </span>
                      <p className="text-xs text-(--text-secondary) line-clamp-1 hover:line-clamp-none transition-all cursor-help">
                        {log.user_agent || t("audit.details.notAvailable")}
                      </p>
                    </div>
                  </div>

                  {log.context && Object.keys(log.context).length > 0 && (
                    <div className="mt-6">
                      <div className="mb-2 flex items-center gap-2 text-label-xs font-bold uppercase tracking-widest text-(--text-secondary) opacity-medium">
                        <Terminal className="h-3 w-3" aria-hidden="true" />
                        <span>{t("audit.details.executionContext")}</span>
                      </div>
                      <div className="rounded-md border border-glass-border/(--opacity-subtle) bg-black/(--opacity-medium) p-4 font-mono text-xs text-brand-light">
                        <pre className="overflow-x-auto whitespace-pre-wrap">
                          {JSON.stringify(log.context, null, 2)}
                        </pre>
                      </div>
                    </div>
                  )}
                </div>
              </m.div>
            </td>
          </tr>
        )}
      </AnimatePresence>
    </>
  )
})

/** Audit-log table with server-backed filters and offset pagination. */
export function AdminAuditFeature() {
  const [page, setPage] = useState(0)
  const rowsPerPage = 50
  const [rawResourceType, setRawResourceType] = useState("")
  const [rawAction, setRawAction] = useState("")
  const [filters, setFilters] = useState({ resource_type: "", action: "" })

  const debouncedResourceType = useDebounced(rawResourceType, "search")
  const debouncedAction = useDebounced(rawAction, "search")

  useEffect(() => {
    setFilters({ resource_type: debouncedResourceType, action: debouncedAction })
    setPage(0)
  }, [debouncedResourceType, debouncedAction])

  const { t } = useTranslation("admin")
  const reducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")

  const { data, isPending: loading } = useAdminAuditLogsQuery(filters, { page, rowsPerPage })
  const logs: AuditLog[] = data?.items ?? []
  const total = data?.total ?? 0

  return (
    <div className="min-h-screen w-full bg-background/(--opacity-medium) py-12">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <m.div
          initial={reducedMotion ? false : { opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={reducedMotion ? { duration: 0 } : undefined}
          className="mb-8"
        >
          <h1 className="text-4xl font-bold tracking-tight text-text-primary sm:text-5xl">
            {t("audit.title")}
          </h1>
          <p className="mt-2 text-base text-(--text-secondary)">{t("audit.subtitle")}</p>
        </m.div>

        {/* Filters */}
        <SectionCard className="mb-6 flex flex-wrap items-end gap-4 p-6">
          <TextField
            id="resource-type-filter"
            label={t("audit.filters.resourceType")}
            value={rawResourceType}
            onChange={(event) => setRawResourceType(event.target.value)}
            className="min-w-(--min-w-column) flex-1"
          />
          <TextField
            id="action-filter"
            label={t("audit.filters.action")}
            value={rawAction}
            onChange={(event) => setRawAction(event.target.value)}
            className="min-w-(--min-w-column) flex-1"
          />
        </SectionCard>

        <div className="overflow-hidden rounded-lg border border-glass-border bg-(--bg-surface)/(--opacity-medium) shadow-glass">
          {loading && logs.length === 0 ? (
            <div className="flex justify-center p-20">
              <div className="h-10 w-10 animate-spin rounded-full border-4 border-brand border-t-transparent" />
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table
                  className="w-full text-left border-collapse"
                  aria-label={t("audit.table.aria")}
                >
                  <thead>
                    <tr className="border-b border-glass-border/(--opacity-subtle) bg-(--bg-surface-hover)/(--opacity-dim)">
                      <th scope="col" className="w-12 px-4 py-4">
                        <span className="sr-only">{t("audit.table.expandColumn")}</span>
                      </th>
                      <th
                        scope="col"
                        className="px-4 py-4 text-xs font-bold uppercase tracking-wider text-(--text-secondary) opacity-strong"
                      >
                        {t("audit.table.time")}
                      </th>
                      <th
                        scope="col"
                        className="px-4 py-4 text-xs font-bold uppercase tracking-wider text-(--text-secondary) opacity-strong"
                      >
                        {t("audit.table.actor")}
                      </th>
                      <th
                        scope="col"
                        className="px-4 py-4 text-xs font-bold uppercase tracking-wider text-(--text-secondary) opacity-strong"
                      >
                        {t("audit.table.action")}
                      </th>
                      <th
                        scope="col"
                        className="px-4 py-4 text-xs font-bold uppercase tracking-wider text-(--text-secondary) opacity-strong"
                      >
                        {t("audit.table.target")}
                      </th>
                      <th
                        scope="col"
                        className="px-4 py-4 text-center text-xs font-bold uppercase tracking-wider text-(--text-secondary) opacity-strong"
                      >
                        {t("audit.table.integrity")}
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-glass-border/(--opacity-subtle)">
                    <AnimatePresence mode="popLayout">
                      {logs.map((log) => (
                        <Row key={log.id} log={log} />
                      ))}
                    </AnimatePresence>
                  </tbody>
                </table>
              </div>

              <div className="flex items-center justify-between border-t border-glass-border/(--opacity-subtle) bg-(--bg-surface)/(--opacity-dim) px-6 py-4">
                <div className="text-sm text-(--text-secondary)" aria-live="polite">
                  {t("audit.pagination.total", { count: total })}
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((currentPage) => Math.max(0, currentPage - 1))}
                    disabled={page === 0}
                  >
                    {t("audit.pagination.previous")}
                  </Button>
                  <span className="flex items-center px-4 text-sm font-medium text-text-primary">
                    {t("audit.pagination.page", { current: page + 1 })}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((currentPage) => currentPage + 1)}
                    disabled={(page + 1) * rowsPerPage >= total}
                  >
                    {t("audit.pagination.next")}
                  </Button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
