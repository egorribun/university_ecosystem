import { useCallback, useMemo, useState } from "react"
import type { ChangeEvent } from "react"
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  CircularProgress,
  FormControlLabel,
  IconButton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip,
  TextField,
  Typography,
} from "@mui/material"
import ReplayIcon from "@mui/icons-material/Replay"
import DeleteIcon from "@mui/icons-material/Delete"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import { useTranslation } from "react-i18next"

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
    setSelected((prev) => {
      const next = new Set(prev)
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
    setSelected((prev) => {
      if (prev.size === items.length) {
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
      setTopicsState((prev) => ({ ...prev, [normalized]: checked }))
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
        <Box py={6} display="flex" justifyContent="center" alignItems="center">
          <CircularProgress aria-label={t("common:loading") ?? "Loading"} />
        </Box>
      )
    }

    if (hasError) {
      return (
        <Alert severity="error" sx={{ mt: 2 }}>
          {getErrorMessage(listQuery.error, t("admin:notifications.errors.fetch"))}
        </Alert>
      )
    }

    if (!jobs.length) {
      return (
        <Alert severity="info" sx={{ mt: 2 }}>
          {t("admin:notifications.empty")}
        </Alert>
      )
    }

    return (
      <TableContainer component={Card} sx={{ mt: 2 }}>
        <Table size="small" aria-label={t("admin:notifications.table.aria") ?? "Dead-letter queue"}>
          <TableHead>
            <TableRow>
              <TableCell padding="checkbox">
                <Checkbox
                  indeterminate={selected.size > 0 && !allSelected}
                  checked={allSelected}
                  onChange={handleSelectAll}
                  inputProps={{
                    "aria-label": t("admin:notifications.table.selectAll") ?? "Select all",
                  }}
                />
              </TableCell>
              <TableCell>{t("admin:notifications.table.columns.kind")}</TableCell>
              <TableCell>{t("admin:notifications.table.columns.record")}</TableCell>
              <TableCell>{t("admin:notifications.table.columns.locale")}</TableCell>
              <TableCell>{t("admin:notifications.table.columns.enqueued")}</TableCell>
              <TableCell>{t("admin:notifications.table.columns.attempts")}</TableCell>
              <TableCell>{t("admin:notifications.table.columns.lastError")}</TableCell>
              <TableCell align="right">{t("admin:notifications.table.columns.actions")}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {jobs.map((job) => {
              const isSelected = selected.has(job.id)
              return (
                <TableRow key={job.id} selected={isSelected} hover>
                  <TableCell padding="checkbox">
                    <Checkbox
                      checked={isSelected}
                      onChange={() => toggleSelect(job.id)}
                      inputProps={{
                        "aria-label":
                          t("admin:notifications.table.selectRow", { id: job.id }) ?? "Select",
                      }}
                    />
                  </TableCell>
                  <TableCell>{formatJobKind(job.kind, t)}</TableCell>
                  <TableCell>{job.record_id}</TableCell>
                  <TableCell>
                    {job.locale ?? t("admin:notifications.table.localeFallback")}
                  </TableCell>
                  <TableCell>
                    {formatDate(new Date(job.enqueued_at), { preset: "datetime" })}
                  </TableCell>
                  <TableCell>{job.attempts}</TableCell>
                  <TableCell>
                    <Typography
                      component="span"
                      sx={{
                        display: "-webkit-box",
                        WebkitBoxOrient: "vertical",
                        WebkitLineClamp: 2,
                        overflow: "hidden",
                      }}
                    >
                      {job.last_error ?? t("admin:notifications.table.noError")}
                    </Typography>
                  </TableCell>
                  <TableCell align="right">
                    <Tooltip title={t("admin:notifications.actions.retry") ?? "Retry"}>
                      <span>
                        <IconButton
                          size="small"
                          onClick={() => retryMutation.mutate([job.id])}
                          disabled={retryMutation.isPending || purgeMutation.isPending}
                          aria-label={
                            t("admin:notifications.actions.retryJob", { id: job.id }) ?? "Retry job"
                          }
                        >
                          <ReplayIcon fontSize="small" />
                        </IconButton>
                      </span>
                    </Tooltip>
                    <Tooltip title={t("admin:notifications.actions.purge") ?? "Delete"}>
                      <span>
                        <IconButton
                          size="small"
                          onClick={() => purgeMutation.mutate([job.id])}
                          disabled={retryMutation.isPending || purgeMutation.isPending}
                          aria-label={
                            t("admin:notifications.actions.purgeJob", { id: job.id }) ??
                            "Delete job"
                          }
                        >
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </span>
                    </Tooltip>
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </TableContainer>
    )
  }

  return (
    <Layout>
      <Box
        sx={{
          width: "100vw",
          minHeight: "100vh",
          bgcolor: "var(--page-bg)",
          color: "var(--page-text)",
          py: { xs: 3.5, sm: 3.5, md: 3.5, lg: 3.5 },
        }}
      >
        <PageFadeIn>
          <Box
            sx={{
              ml: { xs: 2, sm: 4, md: 5, lg: 8 },
              mr: { xs: 2, sm: 4, md: 5, lg: 8 },
              maxWidth: 1200,
              mx: "auto",
            }}
          >
            <Typography
              variant="h4"
              fontWeight={700}
              mb={2}
              color="primary.main"
              sx={{
                textAlign: "left",
                fontSize: "clamp(0.8rem, 5vw, 2.7rem)",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {t("admin:notifications.title")}
            </Typography>
            <Typography variant="body1" color="text.secondary">
              {t("admin:notifications.subtitle")}
            </Typography>
            <Card sx={{ mt: 3 }}>
              <CardContent>
                <Typography variant="h6" fontWeight={600} gutterBottom>
                  {t("admin:notifications.topics.title")}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {t("admin:notifications.topics.description")}
                </Typography>
                <Stack
                  direction={{ xs: "column", sm: "row" }}
                  spacing={2}
                  alignItems={{ xs: "stretch", sm: "flex-end" }}
                  mt={2}
                >
                  <TextField
                    label={t("admin:notifications.topics.userIdLabel")}
                    value={topicsUserIdInput}
                    onChange={(event) => {
                      setTopicsUserIdInput(event.target.value)
                      resetTopicFeedback()
                    }}
                    type="text"
                    // inputProps={{ min: 1 }}
                    sx={{ minWidth: { xs: "100%", sm: 200 } }}
                    disabled={topicsBusy}
                  />
                  <Button variant="contained" onClick={handleLoadTopics} disabled={topicsBusy}>
                    {topicsBusy
                      ? (t("common:loading") ?? "Loading")
                      : t("admin:notifications.topics.load")}
                  </Button>
                </Stack>
                {topicsError && (
                  <Alert severity="error" sx={{ mt: 2 }}>
                    {topicsError}
                  </Alert>
                )}
                {topicsMessage && (
                  <Alert severity="success" sx={{ mt: 2 }}>
                    {topicsMessage}
                  </Alert>
                )}
                {topicsData && (
                  <Box mt={topicsError || topicsMessage ? 2 : 3}>
                    <Typography variant="subtitle1" fontWeight={600} gutterBottom>
                      {t("admin:notifications.topics.userSummary", {
                        email: topicsData.email,
                        id: topicsData.user_id,
                      })}
                    </Typography>
                    <Stack direction={{ xs: "column", sm: "row" }} spacing={1} flexWrap="wrap">
                      {topicsData.allowed_topics.length === 0 ? (
                        <Typography variant="body2" color="text.secondary">
                          {t("admin:notifications.topics.empty")}
                        </Typography>
                      ) : (
                        topicsData.allowed_topics.map((topic) => {
                          const normalized = normalizeTopicKey(topic)
                          const translationKey = `notifications:topics.${normalized}`
                          const label = t(translationKey)
                          const resolvedLabel = label === translationKey ? topic : (label as string)
                          return (
                            <FormControlLabel
                              key={topic}
                              control={
                                <Checkbox
                                  checked={Boolean(topicsState[normalized])}
                                  onChange={handleTopicToggle(topic)}
                                  disabled={topicsBusy}
                                />
                              }
                              label={resolvedLabel}
                            />
                          )
                        })
                      )}
                    </Stack>
                    <Box mt={2}>
                      <Button
                        variant="contained"
                        color="primary"
                        onClick={handleSaveTopics}
                        disabled={topicsBusy || !topicsData.allowed_topics.length}
                      >
                        {topicsBusy
                          ? (t("common:loading") ?? "Loading")
                          : t("admin:notifications.topics.save")}
                      </Button>
                    </Box>
                  </Box>
                )}
              </CardContent>
            </Card>
            <Card sx={{ mt: 3 }}>
              <CardContent>
                <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems="flex-start">
                  <Typography variant="subtitle1" fontWeight={600} sx={{ flexGrow: 1 }}>
                    {t("admin:notifications.total", { count: total })}
                  </Typography>
                  <Stack direction="row" spacing={1}>
                    <Button
                      variant="contained"
                      color="primary"
                      onClick={handleRetrySelected}
                      disabled={disableActions}
                    >
                      {t("admin:notifications.actions.retrySelected")}
                    </Button>
                    <Button
                      variant="outlined"
                      color="secondary"
                      onClick={handlePurgeSelected}
                      disabled={disableActions}
                    >
                      {t("admin:notifications.actions.purgeSelected")}
                    </Button>
                  </Stack>
                </Stack>
                {actionError && (
                  <Alert severity="error" sx={{ mt: 2 }}>
                    {actionError}
                  </Alert>
                )}
                {renderContent()}
              </CardContent>
            </Card>
          </Box>
        </PageFadeIn>
      </Box>
    </Layout>
  )
}
