import { useCallback, useEffect, useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { useTranslation } from "react-i18next"
import dayjs from "dayjs"
import {
  ChevronDown,
  ChevronUp,
  ShieldCheck,
  ShieldAlert,
  Info,
  Terminal,
  User,
  Activity,
  Calendar,
} from "lucide-react"
import api from "../api/client"
import Layout from "../components/Layout"
import { cn } from "@/utils/cn"
import { SectionCard, TextField, Button, Divider } from "@/components/settings"
import { AuditLog, AuditLogList } from "../types/Admin"

function Row({ log }: { log: AuditLog }) {
  const [open, setOpen] = useState(false)
  const { t } = useTranslation("admin")

  const getActionColor = (action: string) => {
    if (action.includes("delete")) return "text-error bg-error/10 border-error/20"
    if (action.includes("create") || action.includes("add"))
      return "text-brand bg-brand/10 border-brand/20"
    if (action.includes("update") || action.includes("modify"))
      return "text-warning bg-warning/10 border-warning/20"
    return "text-secondary-text bg-surface-hover/20 border-glass-border/10"
  }

  return (
    <>
      <tr
        className={cn(
          "transition-colors group",
          log.is_valid ? "hover:bg-surface-hover/5" : "bg-error/5 hover:bg-error/10",
          open && "bg-surface-hover/10"
        )}
      >
        <td className="px-4 py-4">
          <button
            onClick={() => setOpen(!open)}
            className="flex h-8 w-8 items-center justify-center rounded-lg transition-colors hover:bg-surface-hover/20"
          >
            {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>
        </td>
        <td className="px-4 py-4">
          <div className="flex flex-col">
            <span className="text-sm font-bold text-primary-text">
              {dayjs(log.created_at).format("MMM D")}
            </span>
            <span className="text-xs text-secondary-text opacity-70">
              {dayjs(log.created_at).format("HH:mm:ss")}
            </span>
          </div>
        </td>
        <td className="px-4 py-4">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-brand/10 text-brand">
              <User className="h-4 w-4" />
            </div>
            <div className="flex flex-col min-w-0">
              <span className="truncate text-sm font-bold text-primary-text">
                {log.actor_name || t("audit.details.system")}
              </span>
              <span className="truncate text-[10px] uppercase tracking-wider text-secondary-text opacity-50">
                {log.actor_user_id || "SYSTEM"}
              </span>
            </div>
          </div>
        </td>
        <td className="px-4 py-4">
          <span
            className={cn(
              "inline-flex items-center rounded-lg border px-2 py-0.5 text-[0.65rem] font-bold uppercase tracking-wider",
              getActionColor(log.action)
            )}
          >
            {log.action.replace(/\./g, " ").toUpperCase()}
          </span>
        </td>
        <td className="px-4 py-4">
          <div className="flex items-center gap-1.5 text-sm text-secondary-text">
            <Activity className="h-3.5 w-3.5 opacity-50" />
            <span>{log.resource_type}</span>
          </div>
        </td>
        <td className="px-4 py-4 text-center">
          <div className="flex justify-center">
            {log.is_valid ? (
              <div
                className="flex h-6 w-6 items-center justify-center rounded-full bg-brand/10 text-brand"
                title={t("audit.details.integrityVerified")}
              >
                <ShieldCheck className="h-4 w-4" />
              </div>
            ) : (
              <div
                className="flex h-6 w-6 items-center justify-center rounded-full bg-error/10 text-error"
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
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="overflow-hidden"
              >
                <div className="mx-4 mb-4 mt-2 rounded-2xl border border-glass-border bg-surface/50 p-6 shadow-sm">
                  <div className="mb-4 flex items-center gap-2 text-sm font-bold text-primary-text">
                    <Info className="h-4 w-4 text-brand" />
                    <span>{t("audit.details.title")}</span>
                  </div>

                  <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
                    <div className="space-y-1">
                      <span className="text-[10px] font-bold uppercase tracking-widest text-secondary-text opacity-50">
                        {t("audit.details.resourceId")}
                      </span>
                      <p className="text-sm font-mono text-primary-text select-all">
                        {log.resource_id || t("audit.details.notAvailable")}
                      </p>
                    </div>
                    <div className="space-y-1">
                      <span className="text-[10px] font-bold uppercase tracking-widest text-secondary-text opacity-50">
                        {t("audit.details.subject")}
                      </span>
                      <p className="text-sm text-primary-text">
                        {log.subject_name || t("audit.details.notAvailable")}
                        <span className="ml-1 text-xs opacity-50">
                          ({log.subject_user_id || t("audit.details.notAvailable")})
                        </span>
                      </p>
                    </div>
                    <div className="space-y-1">
                      <span className="text-[10px] font-bold uppercase tracking-widest text-secondary-text opacity-50">
                        {t("audit.details.ipAddress")}
                      </span>
                      <p className="text-sm font-mono text-primary-text">
                        {log.ip_address || t("audit.details.unknown")}
                      </p>
                    </div>
                    <div className="space-y-1">
                      <span className="text-[10px] font-bold uppercase tracking-widest text-secondary-text opacity-50">
                        {t("audit.details.userAgent")}
                      </span>
                      <p className="text-xs text-secondary-text line-clamp-1 hover:line-clamp-none transition-all cursor-help">
                        {log.user_agent || t("audit.details.notAvailable")}
                      </p>
                    </div>
                  </div>

                  {log.context && Object.keys(log.context).length > 0 && (
                    <div className="mt-6">
                      <div className="mb-2 flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-secondary-text opacity-50">
                        <Terminal className="h-3 w-3" />
                        <span>{t("audit.details.executionContext")}</span>
                      </div>
                      <div className="rounded-xl border border-glass-border/10 bg-black/40 p-4 font-mono text-xs text-brand-light">
                        <pre className="overflow-x-auto whitespace-pre-wrap">
                          {JSON.stringify(log.context, null, 2)}
                        </pre>
                      </div>
                    </div>
                  )}
                </div>
              </motion.div>
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
  const [rowsPerPage, setRowsPerPage] = useState(50)
  const [filters, setFilters] = useState({ resource_type: "", action: "" })

  const { t } = useTranslation("admin")

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

  const handleChangePage = (direction: "previous" | "next") => {
    if (direction === "previous") setPage(Math.max(0, page - 1))
    else setPage(page + 1)
  }

  return (
    <Layout>
      <div className="min-h-screen w-full bg-background/50 py-12">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-8"
          >
            <h1 className="text-4xl font-bold tracking-tight text-primary-text sm:text-5xl">
              {t("audit.title")}
            </h1>
            <p className="mt-2 text-base text-secondary-text">{t("audit.subtitle")}</p>
          </motion.div>

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
              className="min-w-[200px] flex-1"
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
              className="min-w-[200px] flex-1"
            />
          </SectionCard>

          <div className="overflow-hidden rounded-3xl border border-glass-border bg-surface/40 shadow-glass">
            {loading && logs.length === 0 ? (
              <div className="flex justify-center p-20">
                <div className="h-10 w-10 animate-spin rounded-full border-4 border-brand border-t-transparent" />
              </div>
            ) : (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="border-b border-glass-border/10 bg-surface-hover/20">
                        <th className="w-12 px-4 py-4" />
                        <th className="px-4 py-4 text-xs font-bold uppercase tracking-wider text-secondary-text opacity-70">
                          {t("audit.table.time")}
                        </th>
                        <th className="px-4 py-4 text-xs font-bold uppercase tracking-wider text-secondary-text opacity-70">
                          {t("audit.table.actor")}
                        </th>
                        <th className="px-4 py-4 text-xs font-bold uppercase tracking-wider text-secondary-text opacity-70">
                          {t("audit.table.action")}
                        </th>
                        <th className="px-4 py-4 text-xs font-bold uppercase tracking-wider text-secondary-text opacity-70">
                          {t("audit.table.target")}
                        </th>
                        <th className="px-4 py-4 text-center text-xs font-bold uppercase tracking-wider text-secondary-text opacity-70">
                          {t("audit.table.integrity")}
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-glass-border/10">
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
                <div className="flex items-center justify-between border-t border-glass-border/10 bg-surface/20 px-6 py-4">
                  <div className="text-sm text-secondary-text">
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
                    <span className="flex items-center px-4 text-sm font-medium text-primary-text">
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
