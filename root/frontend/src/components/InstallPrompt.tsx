import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import CloseIcon from "@mui/icons-material/Close"
import {
  Alert,
  Button,
  IconButton,
  Paper,
  Slide,
  Snackbar,
  Stack,
  Typography,
} from "@mui/material"
import { PWA_REFRESH_EVENT, type ServiceWorkerUpdateEventDetail } from "../app/pwaEvents"

interface BeforeInstallPromptEvent extends Event {
  readonly platforms?: string[]
  readonly userChoice: Promise<{ outcome: "accepted" | "dismissed" }>
  prompt: () => Promise<void>
}

type NavigatorStandalone = Navigator & { standalone?: boolean }

const DISMISS_TTL = 1000 * 60 * 60 * 24 * 7
const DISMISS_STORAGE_KEY = "ecosystem.pwa.install.dismissedAt"

const isStandalone = () => {
  if (typeof window === "undefined") return false
  const navigatorWithStandalone = window.navigator as NavigatorStandalone
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    window.matchMedia("(display-mode: minimal-ui)").matches ||
    navigatorWithStandalone.standalone === true
  )
}

const readDismissedAt = () => {
  try {
    const raw = localStorage.getItem(DISMISS_STORAGE_KEY)
    if (!raw) return 0
    const parsed = Number(raw)
    return Number.isFinite(parsed) ? parsed : 0
  } catch {
    return 0
  }
}

const rememberDismiss = () => {
  try {
    localStorage.setItem(DISMISS_STORAGE_KEY, String(Date.now()))
  } catch {
    /* ignore */
  }
}

const clearDismissed = () => {
  try {
    localStorage.removeItem(DISMISS_STORAGE_KEY)
  } catch {
    /* ignore */
  }
}

export default function InstallPrompt() {
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null)
  const [visible, setVisible] = useState(false)
  const [installing, setInstalling] = useState(false)
  const [updateToastOpen, setUpdateToastOpen] = useState(false)
  const suppressUntilRef = useRef<number>(0)
  const pendingUpdateRef = useRef<ServiceWorkerUpdateEventDetail["update"] | null>(null)

  const isEligible = useMemo(() => !isStandalone(), [])

  useEffect(() => {
    const handleServiceWorkerUpdate = (event: Event) => {
      const customEvent = event as CustomEvent<ServiceWorkerUpdateEventDetail>
      pendingUpdateRef.current = customEvent.detail.update
      setUpdateToastOpen(true)
    }

    window.addEventListener(PWA_REFRESH_EVENT, handleServiceWorkerUpdate)

    return () => {
      window.removeEventListener(PWA_REFRESH_EVENT, handleServiceWorkerUpdate)
    }
  }, [])

  useEffect(() => {
    if (!isEligible) return

    suppressUntilRef.current = readDismissedAt() + DISMISS_TTL

    const handleBeforeInstallPrompt = (event: Event) => {
      const now = Date.now()
      if (suppressUntilRef.current && now < suppressUntilRef.current) {
        return
      }

      event.preventDefault()
      setDeferredPrompt(event as BeforeInstallPromptEvent)
      setVisible(true)
    }

    window.addEventListener("beforeinstallprompt", handleBeforeInstallPrompt)

    return () => {
      window.removeEventListener("beforeinstallprompt", handleBeforeInstallPrompt)
    }
  }, [isEligible])

  useEffect(() => {
    if (!isEligible) return

    const onAppInstalled = () => {
      clearDismissed()
      setVisible(false)
      setDeferredPrompt(null)
    }

    window.addEventListener("appinstalled", onAppInstalled)
    return () => window.removeEventListener("appinstalled", onAppInstalled)
  }, [isEligible])

  const handleInstall = useCallback(async () => {
    if (!deferredPrompt) return
    setInstalling(true)
    try {
      await deferredPrompt.prompt()
      const choice = await deferredPrompt.userChoice
      if (choice.outcome === "accepted") {
        clearDismissed()
        setVisible(false)
        setDeferredPrompt(null)
      } else {
        suppressUntilRef.current = Date.now() + DISMISS_TTL
        rememberDismiss()
        setVisible(false)
        setDeferredPrompt(null)
      }
    } catch {
      suppressUntilRef.current = Date.now() + DISMISS_TTL
      rememberDismiss()
      setVisible(false)
      setDeferredPrompt(null)
    } finally {
      setInstalling(false)
    }
  }, [deferredPrompt])

  const handleClose = useCallback(() => {
    suppressUntilRef.current = Date.now() + DISMISS_TTL
    rememberDismiss()
    setVisible(false)
    setDeferredPrompt(null)
  }, [])

  const handleUpdateReload = useCallback(() => {
    const update = pendingUpdateRef.current
    if (!update) return
    setUpdateToastOpen(false)
    void update()
  }, [])

  const handleCloseUpdateToast = useCallback(() => {
    setUpdateToastOpen(false)
  }, [])

  if (!isEligible && !updateToastOpen) return null

  return (
    <>
      <Slide direction="up" in={visible && Boolean(deferredPrompt)} mountOnEnter unmountOnExit>
        <Paper
          elevation={8}
          role="dialog"
          aria-live="polite"
          sx={{
            position: "fixed",
            bottom: { xs: 16, sm: 24 },
            right: { xs: 12, sm: 24 },
            left: { xs: 12, sm: "auto" },
            zIndex: (theme) => theme.zIndex.snackbar,
            maxWidth: 360,
            borderRadius: 3,
            p: 2.5,
            boxShadow: (theme) =>
              theme.palette.mode === "dark"
                ? "0px 18px 45px rgba(11, 15, 22, 0.6)"
                : "0px 18px 45px rgba(11, 99, 244, 0.16)",
          }}
        >
          <Stack spacing={2} alignItems="flex-start">
            <Stack direction="row" spacing={1.5} alignItems="flex-start" sx={{ width: "100%" }}>
              <Typography component="h2" variant="h6" sx={{ flex: 1, fontWeight: 700 }}>
                Установить «Экосистема ГУУ»
              </Typography>
              <IconButton aria-label="Скрыть предложение" onClick={handleClose} size="small">
                <CloseIcon fontSize="small" />
              </IconButton>
            </Stack>
            <Typography variant="body2" sx={{ opacity: 0.85 }}>
              Добавьте приложение на главный экран, чтобы открывать профиль, расписание и новости без браузера.
            </Typography>
            <Stack direction="row" spacing={1.5} sx={{ width: "100%" }}>
              <Button
                variant="contained"
                color="primary"
                onClick={handleInstall}
                disabled={!deferredPrompt || installing}
                sx={{ flexGrow: 1 }}
              >
                Установить
              </Button>
              <Button variant="text" color="inherit" onClick={handleClose}>
                Позже
              </Button>
            </Stack>
          </Stack>
        </Paper>
      </Slide>
      <Snackbar
        open={updateToastOpen}
        onClose={handleCloseUpdateToast}
        autoHideDuration={null}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert
          severity="info"
          variant="filled"
          sx={{ alignItems: "center", gap: 1 }}
          action={
            <Button color="inherit" size="small" onClick={handleUpdateReload}>
              Перезагрузить
            </Button>
          }
        >
          Доступно обновление
        </Alert>
      </Snackbar>
    </>
  )
}
