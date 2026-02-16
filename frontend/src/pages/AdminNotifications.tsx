import { useCallback, useState } from "react"
import type { ChangeEvent } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import { useTranslation } from "react-i18next"
import { RotateCcw, Trash2, Loader2 } from "lucide-react"
import { cn } from "@/utils/cn"
import { Alert, Button, TextField, SectionCard, CircularProgress } from "@/components/settings"

import {
  fetchAdminUserTopics,
  fetchDeadLetterQueue,
  purgeDeadLetterJobs,
  retryDeadLetterJobs,
  updateAdminUserTopics,
} from "@/api/notifications"
import Layout from "@/components/Layout"
import PageFadeIn from "@/components/PageFadeIn"
import { useLocaleFormatters } from "@/i18n/formatters"

const queryKey = ["admin", "notifications", "dead-letter"] as const

function getErrorMessage(error: unknown, fallback: string): string {
  if (isAxiosError(error)) {
    const detail = error.response?.data as { detail?: unknown } | undefined
    const message = detail && typeof detail.detail === "string" ? detail.detail : undefined
    if (message) return message
  }
  if (error instanceof Error && error.message) {
    return error.message
  }
  return fallback
}

const formatJobKind = (kind: string, t: ReturnType<typeof useTranslation>["t"]) => {
  switch (kind) {
    case "event":
      return t("admin:notifications.kinds.event")
    case "news":
      return t("admin:notifications.kinds.news")
    default:
      return kind
  }
}

const normalizeTopicKey = (value: unknown): string => {
  if (typeof value !== "string") return ""
  return value.trim().toLowerCase()
}

export default function AdminNotifications() {
  const { t } = useTranslation(["admin", "common"])
  const { formatDate } = useLocaleFormatters()
  const queryClient = useQueryClient()
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [actionError, setActionError] = useState<string | null>(null)
  const [topicsUserIdInput, setTopicsUserIdInput] = useState("")
  const [topicsData, setTopicsData] = useState<Awaited<
    ReturnType<typeof fetchAdminUserTopics>
  > | null>(null)
  const [topicsState, setTopicsState] = useState<Record<string, boolean>>({})
  const [topicsMessage, setTopicsMessage] = useState<string | null>(null)
  const [topicsError, setTopicsError] = useState<string | null>(null)
  const [topicsBusy, setTopicsBusy] = useState(false)

  const buildTopicState = useCallback(
    (allowed: readonly string[], selectedTopics?: readonly string[] | null) => {
      const normalizedAllowed = Array.from(
        new Set(allowed.map((topic) => normalizeTopicKey(topic)).filter(Boolean))
      )
      const selectedSet = new Set(
        (selectedTopics ?? []).map((topic) => normalizeTopicKey(topic)).filter(Boolean)
      )
      const record: Record<string, boolean> = {}
      for (const topic of normalizedAllowed) {
        record[topic] = selectedSet.has(topic)
      }
      return record
    },
    []
  )

  const listQuery = useQuery({
    queryKey,
    queryFn: () => fetchDeadLetterQueue(),
  })

  const resetSelection = () => setSelected(new Set())

  const onActionError = (error: unknown) => {
    setActionError(getErrorMessage(error, t("admin:notifications.errors.action")))
  }

  const retryMutation = useMutation({
    mutationFn: async (jobIds: string[]) => {
      await retryDeadLetterJobs(jobIds)
    },
    onMutate: () => {
      setActionError(null)
    },
    onSuccess: () => {
      resetSelection()
      void queryClient.invalidateQueries({ queryKey })
    },
    onError: onActionError,
  })

  const purgeMutation = useMutation({
    mutationFn: async (jobIds: string[]) => {
      await purgeDeadLetterJobs(jobIds)
    },
    onMutate: () => {
      setActionError(null)
    },
    onSuccess: () => {
      resetSelection()
      void queryClient.invalidateQueries({ queryKey })
    },
    onError: onActionError,
  })

  const toggleSelect = (jobId: string) => {
    setActionError(null)
    setSelected((previous) => {
      const next = new Set(previous)
      if (next.has(jobId)) {
        next.delete(jobId)
      } else {
        next.add(jobId)
      }
      return next
    })
  }

  const handleSelectAll = () => {
    const items = listQuery.data?.items ?? []
    if (items.length === 0) return
    setSelected((previous) => {
      if (previous.size === items.length) {
        return new Set()
      }
      return new Set(items.map((item) => item.id))
    })
  }

  const resetTopicFeedback = () => {
    setTopicsError(null)
    setTopicsMessage(null)
  }

  const handleLoadTopics = useCallback(async () => {
    const trimmed = topicsUserIdInput.trim()
    if (!trimmed) {
      setTopicsError(t("admin:notifications.topics.invalidId"))
      setTopicsData(null)
      setTopicsState({})
      return
    }
    resetTopicFeedback()
    setTopicsBusy(true)
    try {
      const data = await fetchAdminUserTopics(trimmed)
      setTopicsData(data)
      setTopicsState(buildTopicState(data.allowed_topics, data.topics))
      setTopicsMessage(
        t("admin:notifications.topics.loaded", {
          email: data.email,
          id: data.user_id,
        })
      )
    } catch (error) {
      setTopicsData(null)
      setTopicsState({})
      setTopicsError(getErrorMessage(error, t("admin:notifications.topics.loadError")))
    } finally {
      setTopicsBusy(false)
    }
  }, [buildTopicState, t, topicsUserIdInput])

  const handleTopicToggle = useCallback(
    (topic: string) => (_event: ChangeEvent<HTMLInputElement>, checked: boolean) => {
      const normalized = normalizeTopicKey(topic)
      setTopicsState((previous) => ({ ...previous, [normalized]: checked }))
    },
    []
  )

  const handleSaveTopics = useCallback(async () => {
    if (!topicsData) return
    resetTopicFeedback()
    setTopicsBusy(true)
    try {
      const selectedTopics = topicsData.allowed_topics.filter(
        (topic) => topicsState[normalizeTopicKey(topic)]
      )
      const updated = await updateAdminUserTopics(topicsData.user_id, selectedTopics)
      setTopicsData(updated)
      setTopicsState(buildTopicState(updated.allowed_topics, updated.topics))
      setTopicsMessage(t("admin:notifications.topics.saved"))
    } catch (error) {
      setTopicsError(getErrorMessage(error, t("admin:notifications.topics.saveError")))
    } finally {
      setTopicsBusy(false)
    }
  }, [buildTopicState, t, topicsData, topicsState])

  const handleRetrySelected = () => {
    const ids = Array.from(selected)
    if (!ids.length) return
    retryMutation.mutate(ids)
  }

  const handlePurgeSelected = () => {
    const ids = Array.from(selected)
    if (!ids.length) return
    purgeMutation.mutate(ids)
  }

  const isLoading = listQuery.isLoading
  const hasError = listQuery.isError
  const jobs = listQuery.data?.items ?? []
  const total = listQuery.data?.total ?? 0
  const allSelected = jobs.length > 0 && selected.size === jobs.length

  const disableActions = selected.size === 0 || retryMutation.isPending || purgeMutation.isPending

  const renderContent = () => {
    if (isLoading) {
      return (
        <div className="flex justify-center py-12">
          <CircularProgress />
        </div>
      )
    }

    if (hasError) {
      return (
        <Alert severity="error" className="mt-4">
          {getErrorMessage(listQuery.error, t("admin:notifications.errors.fetch"))}
        </Alert>
      )
    }

    if (!jobs.length) {
      return (
        <Alert severity="info" className="mt-4">
          {t("admin:notifications.empty")}
        </Alert>
      )
    }

    return (
      <div className="mt-4 overflow-hidden rounded-md border border-glass-border bg-(--bg-surface)/(--opacity-medium) shadow-glass">
        <div className="overflow-x-auto">
          <table
            className="w-full text-left border-collapse"
            aria-label={t("admin:notifications.table.aria") ?? "Dead-letter queue"}
          >
            <thead>
              <tr className="border-b border-glass-border/(--opacity-subtle) bg-(--bg-surface-hover)/(--opacity-dim)">
                <th className="px-4 py-3">
                  <input
                    type="checkbox"
                    className="h-4 w-4 rounded border-glass-border bg-(--bg-surface)/(--opacity-medium) text-brand focus:ring-brand/(--opacity-soft)"
                    checked={allSelected}
                    onChange={handleSelectAll}
                    aria-label={t("admin:notifications.table.selectAll") ?? "Select all"}
                  />
                </th>
                <th className="px-4 py-3 text-xs font-bold uppercase tracking-wider text-(--text-secondary) opacity-strong">
                  {t("admin:notifications.table.columns.kind")}
                </th>
                <th className="px-4 py-3 text-xs font-bold uppercase tracking-wider text-(--text-secondary) opacity-strong">
                  {t("admin:notifications.table.columns.record")}
                </th>
                <th className="px-4 py-3 text-xs font-bold uppercase tracking-wider text-(--text-secondary) opacity-strong">
                  {t("admin:notifications.table.columns.locale")}
                </th>
                <th className="px-4 py-3 text-xs font-bold uppercase tracking-wider text-(--text-secondary) opacity-strong">
                  {t("admin:notifications.table.columns.enqueued")}
                </th>
                <th className="px-4 py-3 text-xs font-bold uppercase tracking-wider text-(--text-secondary) opacity-strong">
                  {t("admin:notifications.table.columns.attempts")}
                </th>
                <th className="px-4 py-3 text-xs font-bold uppercase tracking-wider text-(--text-secondary) opacity-strong">
                  {t("admin:notifications.table.columns.lastError")}
                </th>
                <th className="px-4 py-3 text-right text-xs font-bold uppercase tracking-wider text-(--text-secondary) opacity-strong">
                  {t("admin:notifications.table.columns.actions")}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-glass-border/(--opacity-subtle)">
              {jobs.map((job) => {
                const isSelected = selected.has(job.id)
                return (
                  <tr
                    key={job.id}
                    className={cn(
                      "transition-colors hover:bg-(--bg-surface-hover)/(--opacity-subtle)",
                      isSelected && "bg-brand/(--opacity-subtle)"
                    )}
                  >
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        className="h-4 w-4 rounded border-glass-border bg-(--bg-surface)/(--opacity-medium) text-brand focus:ring-brand/(--opacity-soft)"
                        checked={isSelected}
                        onChange={() => toggleSelect(job.id)}
                        aria-label={
                          t("admin:notifications.table.selectRow", { id: job.id }) ?? "Select"
                        }
                      />
                    </td>
                    <td className="px-4 py-3 text-sm text-text-primary">
                      {formatJobKind(job.kind, t)}
                    </td>
                    <td
                      className="px-4 py-3 text-sm text-text-primary font-mono truncate"
                      style={{ maxWidth: "var(--w-label-sm)" }}
                    >
                      {job.record_id}
                    </td>
                    <td className="px-4 py-3 text-sm text-(--text-secondary)">
                      {job.locale ?? t("admin:notifications.table.localeFallback")}
                    </td>
                    <td className="px-4 py-3 text-sm text-(--text-secondary) whitespace-nowrap">
                      {formatDate(new Date(job.enqueued_at), { preset: "datetime" })}
                    </td>
                    <td className="px-4 py-3 text-sm font-bold text-text-primary">
                      {job.attempts}
                    </td>
                    <td
                      className="px-4 py-3 text-sm text-(--text-secondary)"
                      style={{ maxWidth: "var(--w-label-md)" }}
                    >
                      <span
                        className="truncate"
                        style={{ maxWidth: "var(--w-label-sm)" }}
                        title={job.last_error ?? ""}
                      >
                        {job.last_error ?? t("admin:notifications.table.noError")}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right whitespace-nowrap">
                      <div className="flex justify-end gap-1">
                        <button
                          type="button"
                          onClick={() => retryMutation.mutate([job.id])}
                          disabled={retryMutation.isPending || purgeMutation.isPending}
                          className="p-1.5 text-brand hover:bg-brand/(--opacity-subtle) rounded-lg transition-colors disabled:opacity-medium"
                          title={t("admin:notifications.actions.retry")}
                        >
                          <RotateCcw className="h-4 w-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => purgeMutation.mutate([job.id])}
                          disabled={retryMutation.isPending || purgeMutation.isPending}
                          className="p-1.5 text-error hover:bg-error/(--opacity-subtle) rounded-lg transition-colors disabled:opacity-medium"
                          title={t("admin:notifications.actions.purge")}
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    )
  }

  return (
    <Layout>
      <div className="min-h-screen w-full bg-background/(--opacity-medium) py-8">
        <PageFadeIn>
          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
            <div className="mb-8 flex flex-col gap-2">
              <h1 className="text-4xl font-bold tracking-tight text-text-primary sm:text-5xl">
                {t("admin:notifications.title")}
              </h1>
              <p className="text-base text-(--text-secondary)">
                {t("admin:notifications.subtitle")}
              </p>
            </div>

            <SectionCard className="p-6">
              <h2 className="text-lg font-bold tracking-tight text-text-primary mb-1">
                {t("admin:notifications.topics.title")}
              </h2>
              <p className="text-sm text-(--text-secondary) mb-6">
                {t("admin:notifications.topics.description")}
              </p>

              <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
                <TextField
                  label={t("admin:notifications.topics.userIdLabel")}
                  value={topicsUserIdInput}
                  onChange={(event) => {
                    setTopicsUserIdInput(event.target.value)
                    resetTopicFeedback()
                  }}
                  disabled={topicsBusy}
                  className="sm:min-w-(--min-w-filter)"
                />
                <Button
                  onClick={handleLoadTopics}
                  disabled={topicsBusy}
                  className="sm:min-w-(--min-w-btn)"
                >
                  {topicsBusy ? (
                    <div className="flex items-center gap-2">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      <span>{t("common:loading")}</span>
                    </div>
                  ) : (
                    t("admin:notifications.topics.load")
                  )}
                </Button>
              </div>

              {topicsError && (
                <Alert severity="error" className="mt-4">
                  {topicsError}
                </Alert>
              )}
              {topicsMessage && (
                <Alert severity="info" className="mt-4">
                  {topicsMessage}
                </Alert>
              )}

              {topicsData && (
                <div className="mt-8 space-y-6">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-bold text-text-primary">
                      {t("admin:notifications.topics.userSummary", {
                        email: topicsData.email,
                        id: topicsData.user_id,
                      })}
                    </h3>
                  </div>

                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {topicsData.allowed_topics.length === 0 ? (
                      <p className="text-sm text-(--text-secondary)">
                        {t("admin:notifications.topics.empty")}
                      </p>
                    ) : (
                      topicsData.allowed_topics.map((topic) => {
                        const normalized = normalizeTopicKey(topic)
                        const translationKey = `notifications:topics.${normalized}`
                        const label = t(translationKey)
                        const resolvedLabel = label === translationKey ? topic : (label as string)
                        return (
                          <div
                            key={topic}
                            className="flex items-center gap-3 rounded-sm border border-glass-border/(--opacity-subtle) bg-(--bg-surface)/(--opacity-dim) px-4 py-3 transition-colors hover:bg-(--bg-surface)/(--opacity-soft)"
                          >
                            <input
                              type="checkbox"
                              id={`topic-${normalized}`}
                              checked={Boolean(topicsState[normalized])}
                              onChange={(e) =>
                                handleTopicToggle(topic)(
                                  {} as ChangeEvent<HTMLInputElement>,
                                  e.target.checked
                                )
                              }
                              disabled={topicsBusy}
                              className="h-5 w-5 rounded border-glass-border bg-(--bg-surface)/(--opacity-medium) text-brand focus:ring-brand/(--opacity-soft)"
                            />
                            <label
                              htmlFor={`topic-${normalized}`}
                              className="text-sm font-medium text-text-primary leading-none select-none"
                            >
                              {resolvedLabel}
                            </label>
                          </div>
                        )
                      })
                    )}
                  </div>

                  <Button
                    onClick={handleSaveTopics}
                    disabled={topicsBusy || !topicsData.allowed_topics.length}
                    className="min-w-36"
                  >
                    {topicsBusy ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      t("admin:notifications.topics.save")
                    )}
                  </Button>
                </div>
              )}
            </SectionCard>

            <SectionCard className="mt-6 p-6">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h2 className="text-lg font-bold tracking-tight text-text-primary">
                    {t("admin:notifications.total", { count: total })}
                  </h2>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    onClick={handleRetrySelected}
                    disabled={disableActions}
                    variant="outline"
                    className="flex-1 sm:flex-initial"
                  >
                    <RotateCcw className="mr-2 h-4 w-4" />
                    {t("admin:notifications.actions.retrySelected")}
                  </Button>
                  <Button
                    onClick={handlePurgeSelected}
                    disabled={disableActions}
                    variant="outline"
                    className="flex-1 border-error/(--opacity-dim) text-error hover:bg-error/(--opacity-subtle) sm:flex-initial"
                  >
                    <Trash2 className="mr-2 h-4 w-4" />
                    {t("admin:notifications.actions.purgeSelected")}
                  </Button>
                </div>
              </div>

              {actionError && (
                <Alert severity="error" className="mt-4">
                  {actionError}
                </Alert>
              )}

              {renderContent()}
            </SectionCard>
          </div>
        </PageFadeIn>
      </div>
    </Layout>
  )
}
