import { useMemo, useState } from "react"
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  CircularProgress,
  IconButton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from "@mui/material"
import ReplayIcon from "@mui/icons-material/Replay"
import DeleteIcon from "@mui/icons-material/Delete"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import { useTranslation } from "react-i18next"

import apiClient from "@/api/client"
import Layout from "@/components/Layout"
import PageFadeIn from "@/components/PageFadeIn"
import { useLanguage } from "@/contexts/LanguageContext"

type DeadLetterJob = {
  id: number
  kind: string
  record_id: number
  locale: string | null
  enqueued_at: string
  claimed_at: string | null
  attempts: number
  last_error: string | null
  next_retry_at: string | null
}

type DeadLetterResponse = {
  items: DeadLetterJob[]
  total: number
}

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

export default function AdminNotifications() {
  const { language } = useLanguage()
  const { t } = useTranslation(["admin", "common"])
  const queryClient = useQueryClient()
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [actionError, setActionError] = useState<string | null>(null)

  const dateFormatter = useMemo(
    () =>
      new Intl.DateTimeFormat(language, {
        dateStyle: "medium",
        timeStyle: "short",
      }),
    [language]
  )

  const listQuery = useQuery({
    queryKey,
    queryFn: async () => {
      const { data } = await apiClient.get<DeadLetterResponse>(
        "/notifications/admin/dead-letter"
      )
      return data
    },
  })

  const resetSelection = () => setSelected(new Set())

  const onActionError = (error: unknown) => {
    setActionError(getErrorMessage(error, t("admin:notifications.errors.action")))
  }

  const retryMutation = useMutation({
    mutationFn: async (jobIds: number[]) => {
      await apiClient.post("/notifications/admin/dead-letter/retry", { job_ids: jobIds })
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
    mutationFn: async (jobIds: number[]) => {
      await apiClient.post("/notifications/admin/dead-letter/purge", { job_ids: jobIds })
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

  const toggleSelect = (jobId: number) => {
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
                  inputProps={{ "aria-label": t("admin:notifications.table.selectAll") ?? "Select all" }}
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
                      inputProps={{ "aria-label": t("admin:notifications.table.selectRow", { id: job.id }) ?? "Select" }}
                    />
                  </TableCell>
                  <TableCell>{formatJobKind(job.kind, t)}</TableCell>
                  <TableCell>{job.record_id}</TableCell>
                  <TableCell>{job.locale ?? t("admin:notifications.table.localeFallback")}</TableCell>
                  <TableCell>{dateFormatter.format(new Date(job.enqueued_at))}</TableCell>
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
                          aria-label={t("admin:notifications.actions.retryJob", { id: job.id }) ?? "Retry job"}
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
                          aria-label={t("admin:notifications.actions.purgeJob", { id: job.id }) ?? "Delete job"}
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
