import { useCallback, useEffect, useState } from "react"
import { m, AnimatePresence, useReducedMotion } from "framer-motion"
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
import api from "@/api/client"
import Layout from "@/components/Layout"
import { cn } from "@/utils/cn"
import { SectionCard, TextField, Button } from "@/components/settings"
import { AuditLog, AuditLogList } from "@/types/Admin"

function Row({ log }: { log: AuditLog }) {
  const [open, setOpen] = useState(false)
  const { t } = useTranslation("admin")
  const reducedMotion = useReducedMotion()

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
          <button
            type="button"
            id={`audit-row-toggle-${log.id}`}
            onClick={() => setOpen(!open)}
            aria-expanded={open}
            aria-label={open ? t("audit.table.collapseRow") : t("audit.table.expandRow")}
            className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg transition-colors hover:bg-(--bg-surface-hover)/(--opacity-dim) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2"
          >
            {open ? (
              <ChevronUp className="h-4 w-4" aria-hidden="true" />
            ) : (
              <ChevronDown className="h-4 w-4" aria-hidden="true" />
            )}
          </button>
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
              <User className="h-4 w-4" />
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
            <Activity className="h-3.5 w-3.5 opacity-medium" />
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
                <ShieldCheck className="h-4 w-4" />
              </div>
            ) : (
              <div
                className="flex h-6 w-6 items-center justify-center rounded-full bg-error/(--opacity-subtle) text-error"
                title={t("audit.details.integrityTampered")}
              >
                <ShieldAlert className="h-4 w-4" />
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
                    <Info className="h-4 w-4 text-brand" />
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
                        <Terminal className="h-3 w-3" />
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
}

export default function AdminAudit() {
  const [logs, setLogs] = useState<AuditLog[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(0)
  const rowsPerPage = 50
  const [filters, setFilters] = useState({ resource_type: "", action: "" })

  const { t } = useTranslation("admin")
  const reducedMotion = useReducedMotion()

  const fetchLogs = useCallback(async () => {
    setLoading(true)
    try {
      const queryParameters: Record<string, unknown> = {
        limit: rowsPerPage,
        offset: page * rowsPerPage,
      }
      if (filters.resource_type) queryParameters.resource_type = filters.resource_type
      if (filters.action) queryParameters.action = filters.action

      const response = await api.get<AuditLogList>("/admin/audit", { params: queryParameters })
      setLogs(response.data.items)
      setTotal(response.data.total)
    } finally {
      setLoading(false)
    }
  }, [page, rowsPerPage, filters])

  useEffect(() => {
    void fetchLogs()
  }, [fetchLogs])

  return (
    <Layout>
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
              value={filters.resource_type}
              onChange={(event) =>
                setFilters((previousFilters) => ({
                  ...previousFilters,
                  resource_type: event.target.value,
                }))
              }
              className="min-w-(--min-w-column) flex-1"
            />
            <TextField
              id="action-filter"
              label={t("audit.filters.action")}
              value={filters.action}
              onChange={(event) =>
                setFilters((previousFilters) => ({
                  ...previousFilters,
                  action: event.target.value,
                }))
              }
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

                {/* Pagination placeholder as standard table pagination is complex to rewrite from scratch,
                    using a simple layout for now or keeping it minimal */}
                <div className="flex items-center justify-between border-t border-glass-border/(--opacity-subtle) bg-(--bg-surface)/(--opacity-dim) px-6 py-4">
                  <div className="text-sm text-(--text-secondary)">
                    {t("audit.pagination.total", { count: total })}
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setPage(Math.max(0, page - 1))}
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
                      onClick={() => setPage(page + 1)}
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
    </Layout>
  )
}
