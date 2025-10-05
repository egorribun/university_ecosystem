import { useCallback, useEffect, useMemo, useState } from "react"
import Layout from "../components/Layout"
import {
  Avatar,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  IconButton,
  Stack,
  Tooltip,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material"
import ArticleIcon from "@mui/icons-material/Article"
import EventAvailableIcon from "@mui/icons-material/EventAvailable"
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined"
import DoneAllIcon from "@mui/icons-material/DoneAll"
import LaunchIcon from "@mui/icons-material/Launch"
import RefreshIcon from "@mui/icons-material/Refresh"
import NotificationsNoneIcon from "@mui/icons-material/NotificationsNone"
import { alpha } from "@mui/material/styles"
import { useNavigate } from "react-router-dom"
import { useNotifications, type AppNotification } from "@/hooks/useNotifications"

const rtf = new Intl.RelativeTimeFormat("ru-RU", { numeric: "auto" })

type NavigatorWithBadge = Navigator & {
  setAppBadge?: (count?: number) => Promise<void> | void
  clearAppBadge?: () => Promise<void> | void
}

function updateAppBadge(unread: number) {
  if (typeof navigator === "undefined") return
  const nav = navigator as NavigatorWithBadge
  const hasBadgeApi = typeof nav.setAppBadge === "function" || typeof nav.clearAppBadge === "function"
  if (!hasBadgeApi) return

  const swallow = (result: void | Promise<void> | undefined) => {
    if (
      result &&
      typeof (result as PromiseLike<void>).then === "function"
    ) {
      ;(result as PromiseLike<void>).then(undefined, () => {})
    }
  }

  try {
    if (unread > 0) {
      swallow(nav.setAppBadge?.(unread))
      return
    }

    if (typeof nav.clearAppBadge === "function") {
      swallow(nav.clearAppBadge())
    } else {
      swallow(nav.setAppBadge?.(0))
    }
  } catch (error) {
    if (import.meta.env.DEV) {
      console.debug("Failed to update app badge", error)
    }
  }
}

function timeAgo(dateIso: string): string {
  const date = new Date(dateIso)
  const diffMs = date.getTime() - Date.now()
  const diffSec = Math.round(diffMs / 1000)
  const abs = Math.abs(diffSec)
  if (abs < 60) return rtf.format(Math.sign(diffSec) * Math.round(abs), "second")
  if (abs < 3600) return rtf.format(Math.sign(diffSec) * Math.round(abs / 60), "minute")
  if (abs < 86400) return rtf.format(Math.sign(diffSec) * Math.round(abs / 3600), "hour")
  return rtf.format(Math.sign(diffSec) * Math.round(abs / 86400), "day")
}

const typeMeta = {
  news: {
    label: "Новости",
    icon: <ArticleIcon fontSize="small" />,
    color: "info" as const,
  },
  schedule: {
    label: "Расписание",
    icon: <EventAvailableIcon fontSize="small" />,
    color: "success" as const,
  },
  system: {
    label: "Система",
    icon: <InfoOutlinedIcon fontSize="small" />,
    color: "secondary" as const,
  },
  other: {
    label: "Другое",
    icon: <InfoOutlinedIcon fontSize="small" />,
    color: "default" as const,
  },
}

type FilterValue = "all" | "news" | "schedule" | "system" | "other"

function resolveMeta(type?: string | null) {
  if (!type) return typeMeta.system
  if (type in typeMeta) {
    return typeMeta[type as keyof typeof typeMeta]
  }
  return typeMeta.other
}

function NotificationCard({
  notification,
  onOpen,
  onMarkRead,
}: {
  notification: AppNotification
  onOpen: (notification: AppNotification) => void
  onMarkRead: (notification: AppNotification) => void
}) {
  const theme = useTheme()
  const meta = resolveMeta(notification.type)
  const isUnread = !notification.read
  const avatarBg =
    meta.color === "default"
      ? alpha(theme.palette.text.primary, 0.08)
      : alpha(theme.palette[meta.color].main, 0.18)

  return (
    <Card
      variant="outlined"
      sx={{
        borderRadius: 3,
        backgroundColor: isUnread ? alpha(theme.palette.primary.main, 0.06) : "background.paper",
        transition: "background-color 0.2s ease, transform 0.2s ease",
        "&:hover": {
          transform: "translateY(-2px)",
          boxShadow: theme.shadows[4],
        },
      }}
    >
      <CardActionArea onClick={() => onOpen(notification)} sx={{ alignItems: "stretch" }}>
        <CardContent sx={{ display: "flex", gap: 2 }}>
          <Avatar
            sx={{
              bgcolor: avatarBg,
              color:
                meta.color === "default"
                  ? theme.palette.text.primary
                  : theme.palette[meta.color].main,
              width: 48,
              height: 48,
              flexShrink: 0,
            }}
          >
            {meta.icon}
          </Avatar>
          <Stack spacing={1} flex={1} minWidth={0}>
            <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap">
              <Typography
                variant="subtitle1"
                sx={{
                  fontWeight: isUnread ? 700 : 600,
                  lineHeight: 1.2,
                  flexGrow: 1,
                  minWidth: 0,
                }}
              >
                {notification.title}
              </Typography>
              <Chip
                label={meta.label}
                size="small"
                color={meta.color === "default" ? undefined : meta.color}
                variant={meta.color === "default" ? "outlined" : "filled"}
                sx={{
                  fontWeight: 600,
                }}
              />
            </Stack>
            {notification.body && (
              <Typography
                variant="body2"
                color="text.secondary"
                sx={{
                  display: "-webkit-box",
                  WebkitLineClamp: 3,
                  WebkitBoxOrient: "vertical",
                  overflow: "hidden",
                }}
              >
                {notification.body}
              </Typography>
            )}
            <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between">
              <Typography variant="caption" color="text.secondary">
                {timeAgo(notification.created_at)}
              </Typography>
              <Stack direction="row" spacing={1} alignItems="center">
                {isUnread && (
                  <Tooltip title="Пометить прочитанным">
                    <IconButton
                      size="small"
                      onClick={(event) => {
                        event.stopPropagation()
                        onMarkRead(notification)
                      }}
                      aria-label="Пометить как прочитанное"
                    >
                      <DoneAllIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                )}
                {notification.url && (
                  <Tooltip title="Открыть">
                    <LaunchIcon fontSize="small" color="action" />
                  </Tooltip>
                )}
              </Stack>
            </Stack>
          </Stack>
        </CardContent>
      </CardActionArea>
    </Card>
  )
}

function NotificationsCenter() {
  const theme = useTheme()
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"))
  const navigate = useNavigate()
  const {
    items,
    loading,
    hasMore,
    loadMore,
    markRead,
    markAllRead,
    unreadCount,
    refresh,
    fetching,
  } = useNotifications()
  const [filter, setFilter] = useState<FilterValue>("all")
  const [refreshing, setRefreshing] = useState(false)

  useEffect(() => {
    updateAppBadge(unreadCount)
  }, [unreadCount])

  const filteredItems = useMemo(() => {
    if (filter === "all") return items
    if (filter === "other") {
      return items.filter((item) => {
        const meta = resolveMeta(item.type)
        return meta === typeMeta.other
      })
    }
    return items.filter((item) => (item.type ?? "system") === filter)
  }, [items, filter])

  const handleOpen = useCallback(
    (notification: AppNotification) => {
      void markRead(notification.id)
      if (!notification.url) return
      const isExternal = /^https?:\/\//i.test(notification.url)
      if (isExternal) {
        window.open(notification.url, "_blank", "noopener,noreferrer")
        return
      }
      navigate(notification.url)
    },
    [markRead, navigate],
  )

  const handleMarkRead = useCallback(
    (notification: AppNotification) => {
      void markRead(notification.id)
    },
    [markRead],
  )

  const handleRefresh = useCallback(async () => {
    if (refreshing) return
    setRefreshing(true)
    try {
      await refresh()
    } finally {
      setRefreshing(false)
    }
  }, [refresh, refreshing])

  const emptyState = (
    <Stack alignItems="center" spacing={2} py={6} color="text.secondary">
      <NotificationsNoneIcon sx={{ fontSize: 48 }} />
      <Typography variant="h6">Здесь пока нет уведомлений</Typography>
      <Typography variant="body2" color="text.secondary" textAlign="center">
        Как только появятся новости или изменения, мы сразу покажем их здесь.
      </Typography>
    </Stack>
  )

  return (
    <Stack spacing={4}>
      <Stack
        direction={{ xs: "column", sm: "row" }}
        justifyContent="space-between"
        alignItems={{ xs: "flex-start", sm: "center" }}
        spacing={2}
      >
        <Box>
          <Typography variant={isMobile ? "h5" : "h4"} fontWeight={800} gutterBottom>
            Центр уведомлений
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Следите за новостями, изменениями расписания и системными сообщениями в одном месте.
          </Typography>
        </Box>
        <Stack direction="row" spacing={1} alignItems="center">
          <Tooltip title="Обновить">
            <span>
              <IconButton
                onClick={() => void handleRefresh()}
                disabled={refreshing || fetching}
                aria-label="Обновить уведомления"
              >
                {refreshing ? <CircularProgress size={20} /> : <RefreshIcon />}
              </IconButton>
            </span>
          </Tooltip>
          <Button
            variant="contained"
            startIcon={<DoneAllIcon />}
            onClick={() => void markAllRead()}
            disabled={unreadCount === 0}
          >
            Прочитать все
          </Button>
        </Stack>
      </Stack>

      <Stack direction="row" spacing={1} flexWrap="wrap">
        {(
          [
            { value: "all", label: `Все (${items.length})` },
            { value: "news", label: "Новости" },
            { value: "schedule", label: "Расписание" },
            { value: "system", label: "Системные" },
            { value: "other", label: "Другое" },
          ] as Array<{ value: FilterValue; label: string }>
        ).map((chip) => (
          <Chip
            key={chip.value}
            label={chip.label}
            clickable
            color={filter === chip.value ? "primary" : "default"}
            onClick={() => setFilter(chip.value)}
            sx={{ fontWeight: filter === chip.value ? 700 : 500 }}
          />
        ))}
      </Stack>

      <Divider sx={{ opacity: 0.4 }} />

      {loading && !items.length ? (
        <Stack alignItems="center" py={6}>
          <CircularProgress />
        </Stack>
      ) : filteredItems.length === 0 ? (
        emptyState
      ) : (
        <Stack spacing={2.5}>
          {filteredItems.map((notification) => (
            <NotificationCard
              key={notification.id}
              notification={notification}
              onOpen={handleOpen}
              onMarkRead={handleMarkRead}
            />
          ))}
        </Stack>
      )}

      {hasMore && filteredItems.length > 0 && (
        <Box textAlign="center">
          <Button variant="outlined" onClick={() => void loadMore()} disabled={fetching}>
            {fetching ? <CircularProgress size={20} /> : "Показать ещё"}
          </Button>
        </Box>
      )}
    </Stack>
  )
}

export default function NotificationsPage() {
  return (
    <Layout>
      <Box
        sx={{
          width: "100vw",
          minHeight: "100vh",
          boxSizing: "border-box",
          px: { xs: 2, sm: 4, md: 6, lg: 10 },
          py: { xs: 3, sm: 4, md: 5 },
          display: "flex",
          justifyContent: "center",
        }}
      >
        <Box sx={{ width: "min(960px, 100%)" }}>
          <NotificationsCenter />
        </Box>
      </Box>
    </Layout>
  )
}
