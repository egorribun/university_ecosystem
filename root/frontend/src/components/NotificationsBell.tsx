import { useState } from "react"
import {
  Badge,
  IconButton,
  Popover,
  Box,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Button,
  Typography,
} from "@mui/material"
import NotificationsIcon from "@mui/icons-material/Notifications"
import DoneIcon from "@mui/icons-material/Done"
import DeleteSweepIcon from "@mui/icons-material/DeleteSweep"
import { useNotifications } from "@/hooks/useNotifications"
import { useTranslation } from "react-i18next"

export default function NotificationsBell() {
  const { t } = useTranslation(["system"])
  const {
    data,
    unreadCount,
    hasMore,
    nextCursor,
    isLoading,
    markRead,
    markAll,
    clearAll,
    isMarkingAll,
    isClearing,
    isError,
    isRefetching,
    refetch,
    fetchMore,
    isFetchingMore,
    isFetchMoreError,
  } = useNotifications()
  const [anchor, setAnchor] = useState<HTMLElement | null>(null)
  const open = Boolean(anchor)
  const hasNotifications = data.length > 0
  const actionsDisabled =
    isLoading || isError || isRefetching || !hasNotifications || isMarkingAll || isClearing
  return (
    <>
      <IconButton
        color="inherit"
        size="small"
        onClick={(e) => setAnchor(e.currentTarget)}
        aria-label={t("system:notificationsBell.open")}
        sx={{
          width: "clamp(32px, 8vw, 36px)",
          height: "clamp(32px, 8vw, 36px)",
          padding: 0,
          color: "rgba(255, 255, 255, 0.92)",
        }}
      >
        <Badge badgeContent={unreadCount || 0} color="error">
          <NotificationsIcon sx={{ color: "inherit" }} />
        </Badge>
      </IconButton>
      <Popover
        open={open}
        anchorEl={anchor}
        onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "right" }}
        slotProps={{ paper: { sx: { width: 360, maxWidth: "calc(100vw - 24px)" } } }}
      >
        <Box sx={{ p: 1 }}>
          <Box
            sx={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              px: 1,
              py: 0.5,
              gap: 1,
            }}
          >
            <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>
              {t("system:notificationsBell.title")}
            </Typography>
            <Box sx={{ display: "flex", gap: 1 }}>
              <Button
                size="small"
                startIcon={<DoneIcon fontSize="small" />}
                onClick={() => markAll()}
                disabled={actionsDisabled}
              >
                {t("system:notificationsBell.markAll")}
              </Button>
              <Button
                size="small"
                startIcon={<DeleteSweepIcon fontSize="small" />}
                color="error"
                onClick={() =>
                  clearAll(undefined, {
                    onSuccess: () => setAnchor(null),
                  })
                }
                disabled={isLoading || isError || isRefetching || !hasNotifications || isClearing}
              >
                {t("system:notificationsBell.clear")}
              </Button>
            </Box>
          </Box>
          <List dense disablePadding>
            {isError && !isRefetching ? (
              <Box sx={{ p: 2, display: "flex", flexDirection: "column", gap: 1 }}>
                <Typography variant="body2" color="error">
                  {t("system:notificationsBell.error")}
                </Typography>
                <Button size="small" onClick={() => refetch()} disabled={isRefetching}>
                  {t("system:errorBoundary.retry")}
                </Button>
              </Box>
            ) : isLoading || isRefetching ? (
              <Box sx={{ p: 2 }}>
                <Typography variant="body2">{t("system:notificationsBell.loading")}</Typography>
              </Box>
            ) : data.length === 0 ? (
              <Box sx={{ p: 2 }}>
                <Typography variant="body2">{t("system:notificationsBell.empty")}</Typography>
              </Box>
            ) : (
              <>
                {data.map((n) => (
                  <ListItem key={n.id} disablePadding>
                    <ListItemButton
                      component={n.link ? "a" : "div"}
                      href={n.link || undefined}
                      target={n.link ? "_blank" : undefined}
                      rel={n.link ? "noopener noreferrer" : undefined}
                      sx={{
                        opacity: n.read ? 0.6 : 1,
                        alignItems: "flex-start",
                        gap: 1,
                      }}
                      onClick={() => {
                        if (!n.read) markRead(n.id)
                      }}
                    >
                      <ListItemText primary={n.title} secondary={n.body} />
                      {!n.read ? (
                        <Button
                          size="small"
                          sx={{ flexShrink: 0 }}
                          onClick={(e) => {
                            e.preventDefault()
                            e.stopPropagation()
                            markRead(n.id)
                          }}
                        >
                          {t("system:notificationsBell.markRead")}
                        </Button>
                      ) : null}
                    </ListItemButton>
                  </ListItem>
                ))}
                {hasMore ? (
                  <Box
                    sx={{
                      p: 1.5,
                      display: "flex",
                      flexDirection: "column",
                      gap: 1,
                      borderTop: (theme) => `1px solid ${theme.palette.divider}`,
                    }}
                  >
                    {isFetchMoreError ? (
                      <Typography variant="body2" color="error">
                        {t("system:notificationsBell.loadMoreError")}
                      </Typography>
                    ) : null}
                    <Button
                      size="small"
                      variant="outlined"
                      onClick={() => fetchMore(nextCursor)}
                      disabled={!nextCursor || isFetchingMore}
                    >
                      {isFetchingMore
                        ? t("system:notificationsBell.loadingMore")
                        : t("system:notificationsBell.loadMore")}
                    </Button>
                  </Box>
                ) : null}
              </>
            )}
          </List>
        </Box>
      </Popover>
    </>
  )
}
