import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  Avatar,
  Badge,
  Box,
  Button,
  CircularProgress,
  Divider,
  IconButton,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Popover,
  Stack,
  Typography,
} from "@mui/material"
import NotificationsNoneIcon from "@mui/icons-material/NotificationsNone"
import DoneAllIcon from "@mui/icons-material/DoneAll"
import TaskAltIcon from "@mui/icons-material/TaskAlt"
import OpenInNewIcon from "@mui/icons-material/OpenInNew"
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined"
import EventNoteIcon from "@mui/icons-material/EventNote"
import ArticleIcon from "@mui/icons-material/Article"
import FiberManualRecordIcon from "@mui/icons-material/FiberManualRecord"
import SettingsIcon from "@mui/icons-material/Settings"
import NotificationsActiveIcon from "@mui/icons-material/NotificationsActive"
import { useNotifications } from "@/hooks/useNotifications"
import { usePushPreferences } from "@/hooks/usePushPreferences"
import { useNavigate } from "react-router-dom"

type Notif = {
  id: string | number
  title: string
  body?: string
  type?: string
  url?: string
  created_at: string
  read?: boolean
  avatar_url?: string
  icon?: string
}

const rtf = new Intl.RelativeTimeFormat("ru-RU", { numeric: "auto" })
function formatRelTime(iso: string, nowMs: number) {
  const ts = new Date(iso).getTime()
  const diffSec = Math.round((ts - nowMs) / 1000)
  const abs = Math.abs(diffSec)
  if (abs < 60) return rtf.format(Math.sign(diffSec) * Math.round(abs), "second")
  if (abs < 3600) return rtf.format(Math.sign(diffSec) * Math.round(abs / 60), "minute")
  if (abs < 86400) return rtf.format(Math.sign(diffSec) * Math.round(abs / 3600), "hour")
  return rtf.format(Math.sign(diffSec) * Math.round(abs / 86400), "day")
}

function pickIcon(t?: string) {
  if (t === "event") return <EventNoteIcon fontSize="small" />
  if (t === "news") return <ArticleIcon fontSize="small" />
  return <InfoOutlinedIcon fontSize="small" />
}

const TimeAgo = memo(function TimeAgo({ date }: { date: string }) {
  const [, setTick] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setTick((x) => x + 1), 30000)
    return () => clearInterval(id)
  }, [])
  const now = Date.now()
  return <>{formatRelTime(date, now)}</>
})

const NotificationItem = memo(function NotificationItem({
  n,
  onOpen,
  onFocus,
  isActive,
}: {
  n: Notif
  onOpen: (n: Notif, e: React.MouseEvent | React.KeyboardEvent) => void
  onFocus: (n: Notif) => void
  isActive: boolean
}) {
  const unreadDot = !n.read ? <FiberManualRecordIcon sx={{ fontSize: 10, color: "var(--nav-link)" }} /> : null
  const leading = n.avatar_url ? (
    <Avatar src={n.avatar_url} alt="" imgProps={{ loading: "lazy", referrerPolicy: "no-referrer" }} sx={{ width: 28, height: 28 }} />
  ) : (
    pickIcon(n.type)
  )

  return (
    <ListItemButton
      role="listitem"
      data-notification-id={String(n.id)}
      onClick={(e) => onOpen(n, e)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault()
          onOpen(n, e)
        }
      }}
      onFocus={() => onFocus(n)}
      onMouseEnter={() => onFocus(n)}
      selected={isActive}
      sx={(theme) => ({
        alignItems: "flex-start",
        gap: 1,
        py: 1,
        opacity: n.read ? 0.78 : 1,
        backgroundColor: !n.read ? theme.palette.action.hover : undefined,
        "&:hover": { opacity: 1 },
        "&.Mui-selected": {
          backgroundColor: theme.palette.action.selected,
          opacity: 1,
        },
      })}
      aria-label={n.title}
    >
      <ListItemIcon sx={{ minWidth: 34, mt: 0.2 }}>{leading}</ListItemIcon>
      <ListItemText
        primary={
          <Stack direction="row" alignItems="center" spacing={0.8}>
            {!n.read && unreadDot}
            <Typography sx={{ fontWeight: n.read ? 600 : 800, lineHeight: 1.2 }}>{n.title}</Typography>
          </Stack>
        }
        secondary={
          <Stack direction="row" spacing={1} alignItems="center">
            {n.body && (
              <Typography
                variant="body2"
                color="text.secondary"
                sx={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}
              >
                {n.body}
              </Typography>
            )}
            {n.url && <OpenInNewIcon fontSize="inherit" />}
          </Stack>
        }
      />
      <Typography variant="caption" sx={{ whiteSpace: "nowrap", ml: 1 }} title={new Date(n.created_at).toLocaleString()}>
        <TimeAgo date={n.created_at} />
      </Typography>
    </ListItemButton>
  )
})

function PushSettingsPreview({ onOpenSettings }: { onOpenSettings: () => void }) {
  const {
    pushSupported,
    notificationsEnabled,
    pushBusy,
    pushInitializing,
    permissionText,
    enableNotifications,
    disableNotifications,
  } = usePushPreferences()

  const busy = pushBusy || pushInitializing

  const statusText = useMemo(() => {
    if (!pushSupported) return "Веб push-уведомления недоступны в этом браузере."
    if (notificationsEnabled) return "Пуш-уведомления включены."
    return `Разрешение браузера: ${permissionText}.`
  }, [notificationsEnabled, permissionText, pushSupported])

  const hintText = useMemo(() => {
    if (!pushSupported) {
      return "Попробуйте открыть Экосистему ГУУ в другом браузере или установите приложение."
    }
    if (notificationsEnabled) {
      return "Отключить уведомления можно здесь или в настройках браузера."
    }
    return "Разрешите уведомления, чтобы получать новости и изменения сразу."
  }, [notificationsEnabled, pushSupported])

  const handleToggle = useCallback(async () => {
    if (!pushSupported) return
    if (notificationsEnabled) {
      await disableNotifications()
    } else {
      await enableNotifications()
    }
  }, [disableNotifications, enableNotifications, notificationsEnabled, pushSupported])

  return (
    <Stack spacing={1.2}>
      <Stack direction="row" alignItems="center" spacing={1}>
        <NotificationsActiveIcon fontSize="small" color={notificationsEnabled ? "primary" : "disabled"} />
        <Typography variant="subtitle2" fontWeight={700} component="h3">
          Настройки пушей
        </Typography>
      </Stack>
      <Typography variant="body2" color="text.secondary">
        {statusText}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        {hintText}
      </Typography>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
        {pushSupported && (
          <Button
            size="small"
            variant={notificationsEnabled ? "outlined" : "contained"}
            onClick={() => {
              void handleToggle()
            }}
            disabled={busy}
            startIcon={busy ? <CircularProgress size={16} sx={{ color: "inherit" }} /> : undefined}
          >
            {notificationsEnabled ? "Выключить" : "Включить"}
          </Button>
        )}
        <Button
          size="small"
          variant="text"
          onClick={onOpenSettings}
          startIcon={<SettingsIcon fontSize="small" />}
        >
          Подробнее
        </Button>
      </Stack>
    </Stack>
  )
}

export default function NotificationsBell({ iconColor = "inherit" }: { iconColor?: string }) {
  const {
    items,
    loading,
    unreadCount,
    hasMore,
    loadMore,
    markRead,
    markAllRead,
    loadingMore,
  } = useNotifications()
  const [open, setOpen] = useState(false)
  const [selectedId, setSelectedId] = useState<number | string | null>(null)
  const anchorRef = useRef<HTMLButtonElement | null>(null)
  const listRef = useRef<HTMLUListElement | null>(null)
  const scrollBoxRef = useRef<HTMLDivElement | null>(null)
  const sentinelRef = useRef<HTMLDivElement | null>(null)
  const navigate = useNavigate()
  const popoverId = "notifications-popover"
  const titleId = "notifications-title"

  useEffect(() => {
    if (!open) return
    if (!hasMore) return
    const el = sentinelRef.current
    if (!el) return
    const io = new IntersectionObserver(
      (entries) => {
        const vis = entries.some((entry) => entry.isIntersecting)
        if (!vis || loadingMore) return
        void loadMore()
      },
      { root: scrollBoxRef.current, rootMargin: "120px 0px", threshold: 0.01 },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [open, hasMore, loadMore, loadingMore])

  useEffect(() => {
    if (!open) return
    const timer = setTimeout(() => {
      const first = listRef.current?.querySelector<HTMLElement>("[data-notification-id]")
      first?.focus()
    }, 20)
    return () => clearTimeout(timer)
  }, [open, items.length])

  useEffect(() => {
    if (!open) {
      setSelectedId(null)
      return
    }
    setSelectedId((prev) => {
      if (prev != null && items.some((item) => item.id === prev)) return prev
      const next = items.find((item) => !item.read) ?? items[0]
      return next?.id ?? null
    })
  }, [items, open])

  const handleOpenItem = useCallback(
    (n: Notif, e: React.MouseEvent | React.KeyboardEvent) => {
      void markRead(n.id)
      if (!n.url) {
        setOpen(false)
        return
      }
      const isExternal = /^https?:\/\//i.test(n.url)
      const mouse = e as React.MouseEvent
      const isMiddle = (mouse as any).button === 1
      const newTab = mouse.ctrlKey || mouse.metaKey || isMiddle
      if (isExternal) {
        if (newTab) window.open(n.url, "_blank", "noopener,noreferrer")
        else window.open(n.url, "_self")
      } else {
        if (newTab) window.open(n.url, "_blank")
        else navigate(n.url)
      }
      setOpen(false)
    },
    [markRead, navigate],
  )

  const handleFocusItem = useCallback((n: Notif) => {
    setSelectedId(n.id)
  }, [])

  const handleListKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLUListElement>) => {
      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return
      if (!items.length) return
      event.preventDefault()
      const dir = event.key === "ArrowDown" ? 1 : -1
      const currentIndex = selectedId != null ? items.findIndex((item) => item.id === selectedId) : -1
      let nextIndex = currentIndex + dir
      if (nextIndex < 0) nextIndex = items.length - 1
      if (nextIndex >= items.length) nextIndex = 0
      const next = items[nextIndex]
      if (next) {
        setSelectedId(next.id)
        const el = listRef.current?.querySelector<HTMLElement>(`[data-notification-id="${next.id}"]`)
        el?.focus()
      }
    },
    [items, selectedId],
  )

  const selectedNotification = useMemo(() => {
    if (selectedId == null) return undefined
    return items.find((item) => item.id === selectedId)
  }, [items, selectedId])

  const handleMarkSelected = useCallback(() => {
    if (!selectedNotification || selectedNotification.read) return
    void markRead(selectedNotification.id)
  }, [markRead, selectedNotification])

  const handleMarkAll = useCallback(() => {
    void markAllRead()
  }, [markAllRead])

  const handleOpenSettings = useCallback(() => {
    setOpen(false)
    navigate("/settings")
  }, [navigate])

  const handleOpenCenter = useCallback(() => {
    setOpen(false)
    navigate("/notifications")
  }, [navigate])

  const renderList = () => {
    if (loading && !items.length) {
      return (
        <Stack alignItems="center" justifyContent="center" sx={{ py: 3 }}>
          <CircularProgress size={26} />
        </Stack>
      )
    }
    if (items.length === 0) {
      return (
        <Stack alignItems="center" justifyContent="center" sx={{ py: 4, color: "text.secondary" }} role="status" aria-live="polite">
          <NotificationsNoneIcon />
          <Typography mt={1}>Здесь пока пусто</Typography>
        </Stack>
      )
    }
    return (
      <>
        <List
          ref={listRef}
          disablePadding
          role="list"
          aria-labelledby={titleId}
          sx={{ py: 0 }}
          onKeyDown={handleListKeyDown}
        >
          {items.map((n) => (
            <NotificationItem key={n.id} n={n} onOpen={handleOpenItem} onFocus={handleFocusItem} isActive={selectedId === n.id} />
          ))}
        </List>
        {(hasMore || loadingMore) && (
          <Box sx={{ p: 1.2 }}>
            {loadingMore ? (
              <Stack alignItems="center" sx={{ py: 1 }}>
                <CircularProgress size={22} />
              </Stack>
            ) : (
              <Button fullWidth variant="outlined" onClick={() => void loadMore()} aria-busy={loadingMore}>
                Показать ещё
              </Button>
            )}
            <div ref={sentinelRef} aria-hidden="true" style={{ height: 1 }} />
          </Box>
        )}
      </>
    )
  }

  return (
    <>
      <IconButton
        ref={anchorRef}
        onClick={() => setOpen((v) => !v)}
        aria-label={`Открыть уведомления${unreadCount > 0 ? `, непрочитанных: ${unreadCount}` : ", непрочитанных нет"}`}
        aria-haspopup="dialog"
        aria-controls={open ? popoverId : undefined}
        aria-expanded={open ? "true" : "false"}
        sx={{ ml: { xs: 0.5, sm: 1 }, color: iconColor }}
      >
        <Badge color="error" badgeContent={unreadCount} max={99} overlap="circular">
          <NotificationsNoneIcon />
        </Badge>
      </IconButton>

      <Popover
        id={popoverId}
        open={open}
        onClose={() => setOpen(false)}
        anchorEl={anchorRef.current}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
        transformOrigin={{ vertical: "top", horizontal: "center" }}
        PaperProps={{
          role: "dialog",
          "aria-modal": "true",
          "aria-labelledby": titleId,
          sx: { width: 400, maxWidth: "92vw", bgcolor: "var(--card-bg)" },
        }}
        disableRestoreFocus={false}
      >
        <Box sx={{ p: 1.5 }}>
          <Stack spacing={0.5}>
            <Typography id={titleId} fontWeight={800} fontSize="1rem">
              Уведомления
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {unreadCount > 0 ? `Непрочитанных: ${unreadCount}` : "Все уведомления прочитаны."}
            </Typography>
          </Stack>
        </Box>
        <Divider />
        <Box sx={{ px: 1.5, py: 1 }}>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ sm: "stretch" }}>
            <Button
              variant="outlined"
              size="small"
              startIcon={<TaskAltIcon fontSize="small" />}
              onClick={handleMarkSelected}
              disabled={!selectedNotification || selectedNotification.read}
            >
              Пометить прочитанным
            </Button>
            <Button
              variant="outlined"
              size="small"
              startIcon={<DoneAllIcon fontSize="small" />}
              onClick={handleMarkAll}
              disabled={unreadCount === 0}
            >
              Пометить все прочитанными
            </Button>
            <Button
              variant="outlined"
              size="small"
              startIcon={<SettingsIcon fontSize="small" />}
              onClick={handleOpenSettings}
            >
              Открыть настройки уведомлений
            </Button>
          </Stack>
        </Box>
        <Divider />
        <Box ref={scrollBoxRef} sx={{ maxHeight: 444, overflow: "auto" }}>
          {renderList()}
        </Box>
        <Divider />
        <Box sx={{ p: 1 }}>
          <Button
            fullWidth
            variant="text"
            onClick={handleOpenCenter}
          >
            Открыть центр уведомлений
          </Button>
        </Box>
        {open && (
          <>
            <Divider />
            <Box sx={{ px: 1.5, py: 1.5 }}>
              <PushSettingsPreview onOpenSettings={handleOpenSettings} />
            </Box>
          </>
        )}
      </Popover>
    </>
  )
}
