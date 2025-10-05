import { useEffect, useRef, useState, useCallback, ChangeEvent, useMemo } from "react";
import { useAuth, currentUserQueryKey, fetchCurrentUser } from "@/contexts/AuthContext";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useNotifications } from "@/hooks/useNotifications";
import api from "../api/client";
import {
  Box,
  Paper,
  Tabs,
  Tab,
  Stack,
  Typography,
  Button,
  Chip,
  Snackbar,
  Alert,
  RadioGroup,
  FormControlLabel,
  Radio,
  Divider,
  Avatar,
  List,
  ListItem,
  ListItemText,
  ListItemAvatar,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Switch,
  FormGroup,
  FormControl,
  FormHelperText
} from "@mui/material";
import { useColorScheme } from "@mui/material/styles";
import SettingsIcon from "@mui/icons-material/Settings";
import DarkModeIcon from "@mui/icons-material/DarkMode";
import LightModeIcon from "@mui/icons-material/LightMode";
import DesktopWindowsIcon from "@mui/icons-material/DesktopWindows";
import LogoutIcon from "@mui/icons-material/Logout";
import PhotoCameraIcon from "@mui/icons-material/PhotoCamera";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import ImageIcon from "@mui/icons-material/Image";
import NotificationsActiveIcon from "@mui/icons-material/NotificationsActive";
import NotificationsOffIcon from "@mui/icons-material/NotificationsOff";
import defaultAvatar from "@/assets/default_avatar.png";
import spotifyLogo from "@/assets/spotify_icon.png";
import { resolveMediaUrl } from "@/utils/media";
import {
  getExistingPushSubscription,
  isPushSupported,
  setPushConsent,
  urlBase64ToUint8Array
} from "@/push/subscribe";
import { deleteSubscription, getVapidKey, saveSubscription } from "@/api/notifications";

type ThemeMode = "system" | "light" | "dark";

const BACKEND_ORIGIN = import.meta.env.VITE_BACKEND_ORIGIN || "";

type NotificationTopicKey = "news" | "schedule" | "system";

const NOTIFICATION_TOPIC_LABELS: Record<NotificationTopicKey, string> = {
  news: "Новости",
  schedule: "Расписание",
  system: "Системные"
};

const DEFAULT_NOTIFICATION_TOPICS: Record<NotificationTopicKey, boolean> = {
  news: true,
  schedule: true,
  system: true
};

export default function Settings() {
  const navigate = useNavigate();
  const { user, setUser, logout } = useAuth();
  const queryClient = useQueryClient();
  const { unreadCount } = useNotifications();
  const [tab, setTab] = useState(0);
  const [snack, setSnack] = useState<{ text: string; sev?: "success" | "info" | "warning" | "error" } | null>(null);

  const { mode: storedMode, setMode } = useColorScheme();
  const theme = (storedMode ?? "system") as ThemeMode;

  const topicKeys = useMemo(() => Object.keys(NOTIFICATION_TOPIC_LABELS) as NotificationTopicKey[], []);
  const [topicState, setTopicState] = useState<Record<NotificationTopicKey, boolean>>(DEFAULT_NOTIFICATION_TOPICS);
  const [pushSupported, setPushSupported] = useState(() => isPushSupported());
  const [notificationPermission, setNotificationPermission] = useState<NotificationPermission>(() => {
    if (typeof window === "undefined" || typeof Notification === "undefined") return "default";
    return Notification.permission;
  });
  const [pushSubscription, setPushSubscription] = useState<PushSubscription | null>(null);
  const [pushBusy, setPushBusy] = useState(false);
  const [pushInitializing, setPushInitializing] = useState(true);

  const selectedTopics = useMemo(() => {
    return topicKeys.filter(key => topicState[key]);
  }, [topicKeys, topicState]);

  const permissionText = useMemo(() => {
    switch (notificationPermission) {
      case "granted":
        return "разрешено";
      case "denied":
        return "запрещено";
      default:
        return "не запрошено";
    }
  }, [notificationPermission]);

  const selectedTopicsDescription = useMemo(() => {
    if (!selectedTopics.length) return "Темы не выбраны";
    return selectedTopics.map(key => NOTIFICATION_TOPIC_LABELS[key]).join(", ");
  }, [selectedTopics]);

  const notificationsEnabled = !!pushSubscription;

  const applyServerTopics = useCallback(
    (topics?: string[] | null) => {
      if (topics == null) return;
      const next: Record<NotificationTopicKey, boolean> = {} as Record<NotificationTopicKey, boolean>;
      for (const key of topicKeys) {
        next[key] = false;
      }
      for (const rawTopic of topics) {
        if (!rawTopic) continue;
        const normalized = rawTopic.toString().trim().toLowerCase() as NotificationTopicKey;
        if ((topicKeys as string[]).includes(normalized)) {
          next[normalized as NotificationTopicKey] = true;
        }
      }
      setTopicState(next);
    },
    [topicKeys]
  );

  const handleThemeChange = useCallback(
    (_: ChangeEvent<HTMLInputElement>, value: string) => {
      setMode(value as ThemeMode);
    },
    [setMode]
  );

  const enableNotifications = useCallback(async () => {
    if (!isPushSupported()) {
      setPushSupported(false);
      setSnack({ text: "Ваш браузер не поддерживает push-уведомления", sev: "warning" });
      return;
    }
    if (typeof Notification === "undefined") {
      setSnack({ text: "Браузер не поддерживает уведомления", sev: "warning" });
      return;
    }
    setPushBusy(true);
    try {
      const permission = await Notification.requestPermission();
      setNotificationPermission(permission);
      if (permission !== "granted") {
        setSnack({ text: "Разрешите уведомления в настройках браузера", sev: "info" });
        return;
      }

      if (!("serviceWorker" in navigator)) {
        setSnack({ text: "Сервис-воркеры недоступны", sev: "error" });
        return;
      }

      const registration = await navigator.serviceWorker.ready;
      let sub = await registration.pushManager.getSubscription();

      if (!sub) {
        let vapidKey = "";
        try {
          vapidKey = (await getVapidKey())?.trim() || "";
        } catch (error) {
          console.error("Failed to load VAPID key", error);
        }
        if (!vapidKey) {
          setSnack({ text: "Не удалось получить ключ уведомлений", sev: "error" });
          return;
        }
        const applicationServerKey = urlBase64ToUint8Array(vapidKey);
        sub = await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey
        });
      }

      if (!sub) {
        setSnack({ text: "Не удалось активировать подписку", sev: "error" });
        return;
      }

      type Payload = Parameters<typeof saveSubscription>[0];
      const saved = await saveSubscription(sub.toJSON() as Payload, selectedTopics);
      applyServerTopics(saved?.topics ?? selectedTopics);
      setPushSubscription(sub);
      setPushConsent(true);
      setSnack({ text: "Уведомления включены", sev: "success" });
    } catch (error) {
      console.error("Failed to enable notifications", error);
      setSnack({ text: "Не удалось включить уведомления", sev: "error" });
    } finally {
      setPushBusy(false);
      setPushInitializing(false);
    }
  }, [applyServerTopics, selectedTopics]);

  const disableNotifications = useCallback(async () => {
    if (!isPushSupported()) {
      setPushSubscription(null);
      setPushConsent(false);
      return;
    }
    setPushBusy(true);
    try {
      const registration = await navigator.serviceWorker.ready;
      const sub = await registration.pushManager.getSubscription();
      if (!sub) {
        setPushSubscription(null);
        setPushConsent(false);
        setSnack({ text: "Уведомления выключены", sev: "success" });
        return;
      }
      const endpoint = sub.endpoint;
      let unsubscribed = false;
      try {
        unsubscribed = await sub.unsubscribe();
      } catch (error) {
        console.error("Failed to unsubscribe push", error);
      }
      if (endpoint) {
        try {
          await deleteSubscription(endpoint);
        } catch (error) {
          console.warn("Не удалось удалить подписку на сервере", error);
        }
      }
      setPushSubscription(null);
      setPushConsent(false);
      if (unsubscribed || !endpoint) {
        setSnack({ text: "Уведомления выключены", sev: "success" });
      } else {
        setSnack({ text: "Уведомления отключены локально", sev: "info" });
      }
    } catch (error) {
      console.error("Failed to disable notifications", error);
      setSnack({ text: "Не удалось выключить уведомления", sev: "error" });
    } finally {
      setPushBusy(false);
    }
  }, []);

  const handleNotificationsToggle = useCallback(
    (_: ChangeEvent<HTMLInputElement>, checked: boolean) => {
      if (pushBusy || pushInitializing) return;
      if (checked) void enableNotifications();
      else void disableNotifications();
    },
    [disableNotifications, enableNotifications, pushBusy, pushInitializing]
  );

  const handleTopicToggle = useCallback(
    (key: NotificationTopicKey) =>
      (_: ChangeEvent<HTMLInputElement>, checked: boolean) => {
        const nextState = { ...topicState, [key]: checked };
        setTopicState(nextState);
        if (!notificationsEnabled || pushBusy) return;
        if (!isPushSupported()) return;
        setPushBusy(true);
        const topicsToSend = topicKeys.filter(topic => nextState[topic]);
        type Payload = Parameters<typeof saveSubscription>[0];
        (async () => {
          try {
            const registration = await navigator.serviceWorker.ready;
            const sub = await registration.pushManager.getSubscription();
            if (!sub) {
              setPushSubscription(null);
              setPushConsent(false);
              return;
            }
            const saved = await saveSubscription(sub.toJSON() as Payload, topicsToSend);
            applyServerTopics(saved?.topics ?? topicsToSend);
            setPushSubscription(sub);
          } catch (error) {
            console.error("Failed to update topics", error);
            setSnack({ text: "Не удалось обновить настройки уведомлений", sev: "error" });
          } finally {
            setPushBusy(false);
          }
        })();
      },
    [applyServerTopics, notificationsEnabled, pushBusy, topicKeys, topicState]
  );

  useEffect(() => {
    const sp = new URLSearchParams(window.location.search);
    const s = sp.get("spotify");
    if (s) {
      if (s === "connected") setSnack({ text: "Spotify подключён", sev: "success" });
      if (s === "error") setSnack({ text: "Ошибка подключения Spotify", sev: "error" });
      sp.delete("spotify");
      const next = window.location.pathname + (sp.toString() ? "?" + sp : "");
      window.history.replaceState({}, "", next);
    }
  }, []);

  useEffect(() => {
    setPushSupported(isPushSupported());
  }, []);

  useEffect(() => {
    let cancelled = false;
    let removeListener: (() => void) | undefined;

    const syncPermission = () => {
      if (typeof Notification === "undefined") {
        setNotificationPermission("default");
        return;
      }
      setNotificationPermission(Notification.permission);
    };
    syncPermission();

    if (typeof navigator !== "undefined" && (navigator as any).permissions?.query) {
      (navigator as any)
        .permissions.query({ name: "notifications" as PermissionName })
        .then((status: PermissionStatus) => {
          if (cancelled) return;
          const handler = () => {
            if (cancelled) return;
            const state = status.state;
            if (state === "prompt") setNotificationPermission("default");
            else setNotificationPermission(state as NotificationPermission);
          };
          handler();
          if (typeof status.addEventListener === "function") {
            status.addEventListener("change", handler);
            removeListener = () => {
              try {
                status.removeEventListener("change", handler);
              } catch {}
            };
          } else {
            const statusWithOnChange = status as PermissionStatus & { onchange?: (() => void) | null };
            statusWithOnChange.onchange = handler;
            removeListener = () => {
              if (statusWithOnChange.onchange === handler) {
                statusWithOnChange.onchange = null;
              }
            };
          }
        })
        .catch(() => {});
    }

    return () => {
      cancelled = true;
      removeListener?.();
    };
  }, []);

  useEffect(() => {
    let active = true;
    const detectSubscription = async () => {
      try {
        const supported = isPushSupported();
        if (!active) return;
        setPushSupported(supported);
        if (!supported) {
          setPushSubscription(null);
          return;
        }
        setPushInitializing(true);
        const sub = await getExistingPushSubscription();
        if (!active) return;
        setPushSubscription(sub);
        if (sub) {
          setPushConsent(true);
          type Payload = Parameters<typeof saveSubscription>[0];
          try {
            const saved = await saveSubscription(sub.toJSON() as Payload);
            if (!active) return;
            applyServerTopics(saved?.topics ?? []);
          } catch (error) {
            console.warn("Не удалось получить настройки подписки", error);
          }
        }
      } catch (error) {
        if (active) {
          console.warn("Не удалось определить подписку на push", error);
        }
      } finally {
        if (active) setPushInitializing(false);
      }
    };
    void detectSubscription();
    return () => {
      active = false;
    };
  }, [applyServerTopics]);

  const spotifyConnected = Boolean((user as any)?.spotify_connected || (user as any)?.spotify_is_connected);
  const spotifyName = (user as any)?.spotify_display_name || "";

  const connectSpotify = async () => {
    try {
      const r = await api.get<{ url: string }>("/spotify/auth-url");
      if (r.data?.url) window.location.assign(r.data.url);
    } catch {
      setSnack({ text: "Не удалось открыть авторизацию Spotify", sev: "error" });
    }
  };

  const disconnectSpotify = async () => {
    try {
      await api.post("/spotify/disconnect");
      const me = await queryClient.fetchQuery({
        queryKey: currentUserQueryKey,
        queryFn: fetchCurrentUser,
      });
      setUser(me);
      setSnack({ text: "Spotify отключён", sev: "success" });
    } catch {
      setSnack({ text: "Не удалось отключить Spotify", sev: "error" });
    }
  };

  const isImage = (f: File) => /^image\/(png|jpe?g|webp|gif|avif)$/i.test(f.type);
  const withinSize = (f: File, maxMB = 12) => f.size / (1024 * 1024) <= maxMB;

  const avatarInputRef = useRef<HTMLInputElement | null>(null);
  const coverInputRef = useRef<HTMLInputElement | null>(null);
  const [avatarBusy, setAvatarBusy] = useState(false);
  const [coverBusy, setCoverBusy] = useState(false);

  const getAvatarSrc = useCallback(() => {
    if ((user as any)?.avatar_url) {
      const url = resolveMediaUrl((user as any).avatar_url, BACKEND_ORIGIN);
      return url;
    }
    return defaultAvatar;
  }, [user]);

  const getCoverSrc = useCallback(() => {
    if ((user as any)?.cover_url) {
      const url = resolveMediaUrl((user as any).cover_url, BACKEND_ORIGIN);
      return url;
    }
    return "";
  }, [user]);

  const triggerAvatarPick = () => avatarInputRef.current?.click();
  const triggerCoverPick = () => coverInputRef.current?.click();

  const uploadAvatar = async (file: File) => {
    if (!isImage(file)) return setSnack({ text: "Поддерживаются PNG/JPG/WebP/AVIF/GIF", sev: "warning" });
    if (!withinSize(file)) return setSnack({ text: "Файл слишком большой (>12 МБ)", sev: "warning" });
    try {
      setAvatarBusy(true);
      const fd = new FormData();
      fd.append("file", file);
      await api.post("/users/me/avatar", fd, { headers: { "Content-Type": "multipart/form-data" } });
      const me = await queryClient.fetchQuery({
        queryKey: currentUserQueryKey,
        queryFn: fetchCurrentUser,
      });
      setUser(me);
      setSnack({ text: "Аватар обновлён", sev: "success" });
    } catch {
      setSnack({ text: "Не удалось загрузить аватар", sev: "error" });
    } finally {
      setAvatarBusy(false);
    }
  };

  const removeAvatar = async () => {
    try {
      setAvatarBusy(true);
      await api.delete("/users/me/avatar");
      const me = await queryClient.fetchQuery({
        queryKey: currentUserQueryKey,
        queryFn: fetchCurrentUser,
      });
      setUser(me);
      setSnack({ text: "Аватар удалён", sev: "success" });
    } catch {
      setSnack({ text: "Не удалось удалить аватар", sev: "error" });
    } finally {
      setAvatarBusy(false);
    }
  };

  const uploadCover = async (file: File) => {
    if (!isImage(file)) return setSnack({ text: "Поддерживаются PNG/JPG/WebP/AVIF/GIF", sev: "warning" });
    if (!withinSize(file)) return setSnack({ text: "Файл слишком большой (>12 МБ)", sev: "warning" });
    try {
      setCoverBusy(true);
      const fd = new FormData();
      fd.append("file", file);
      await api.post("/users/me/cover", fd, { headers: { "Content-Type": "multipart/form-data" } });
      const me = await queryClient.fetchQuery({
        queryKey: currentUserQueryKey,
        queryFn: fetchCurrentUser,
      });
      setUser(me);
      setSnack({ text: "Обложка обновлена", sev: "success" });
    } catch {
      setSnack({ text: "Не удалось загрузить обложку", sev: "error" });
    } finally {
      setCoverBusy(false);
    }
  };

  const [confirmLogout, setConfirmLogout] = useState(false);

  return (
    <Box maxWidth="100vw" mx={0} mt={0} width="100vw" minHeight="100svh" px={0}>
      <Paper
        className="glass glass--panel"
        sx={{
          p: { xs: 2, md: 4, lg: 6 },
          borderRadius: 0,
          width: "100%",
          minHeight: "100svh",
          color: "var(--page-text)",
          bgcolor: "var(--card-bg)"
        }}
      >
        <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: { xs: 1.5, md: 2 } }}>
          <SettingsIcon />
          <Typography variant="h4" fontWeight={800} sx={{ color: "var(--page-text)" }}>
            Настройки
          </Typography>
        </Stack>

        <Paper variant="outlined" className="glass--segmented" sx={{ mb: 3, bgcolor: "var(--card-bg)" }}>
          <Tabs
            value={tab}
            onChange={(_, v) => setTab(v)}
            variant="scrollable"
            scrollButtons="auto"
            sx={{
              "& .MuiTab-root": {
                color: "var(--page-text)",
                textTransform: "none",
                fontWeight: 700,
                minHeight: 42
              },
              "& .Mui-selected": { color: "var(--link-color)" }
            }}
          >
            <Tab label="Общее" />
            <Tab label="Аккаунт" />
            <Tab label="Интеграции" />
          </Tabs>
        </Paper>

        {tab === 0 && (
          <Stack spacing={3}>
            <Box>
              <Typography variant="h6" sx={{ mb: 1.2, color: "var(--page-text)" }}>
                Тема
              </Typography>
              <RadioGroup row value={theme} onChange={handleThemeChange}>
                <FormControlLabel
                  value="system"
                  control={<Radio />}
                  label={
                    <Stack direction="row" alignItems="center" spacing={1} sx={{ color: "var(--page-text)" }}>
                      <DesktopWindowsIcon /> <span>Система</span>
                    </Stack>
                  }
                  sx={{ "& .MuiFormControlLabel-label": { color: "var(--page-text)" } }}
                />
                <FormControlLabel
                  value="light"
                  control={<Radio />}
                  label={
                    <Stack direction="row" alignItems="center" spacing={1} sx={{ color: "var(--page-text)" }}>
                      <LightModeIcon /> <span>Светлая</span>
                    </Stack>
                  }
                  sx={{ "& .MuiFormControlLabel-label": { color: "var(--page-text)" } }}
                />
                <FormControlLabel
                  value="dark"
                  control={<Radio />}
                  label={
                    <Stack direction="row" alignItems="center" spacing={1} sx={{ color: "var(--page-text)" }}>
                      <DarkModeIcon /> <span>Тёмная</span>
                    </Stack>
                  }
                  sx={{ "& .MuiFormControlLabel-label": { color: "var(--page-text)" } }}
                />
              </RadioGroup>
            </Box>

            <Divider />

            <Box>
              <Typography variant="h6" sx={{ mb: 1.2, color: "var(--page-text)" }}>
                Уведомления
              </Typography>
              {!pushSupported ? (
                <Alert severity="warning" variant="outlined">
                  Веб push-уведомления недоступны в вашем браузере.
                </Alert>
              ) : (
                <Stack spacing={1.8}>
                  <FormControl component="fieldset" variant="standard">
                    <FormGroup>
                      <FormControlLabel
                        control={
                          <Switch
                            checked={notificationsEnabled}
                            onChange={handleNotificationsToggle}
                            disabled={pushBusy || pushInitializing}
                          />
                        }
                        label={
                          <Stack direction="row" alignItems="center" spacing={1} sx={{ color: "var(--page-text)" }}>
                            {notificationsEnabled ? <NotificationsActiveIcon /> : <NotificationsOffIcon />}
                            <span>Включить уведомления</span>
                          </Stack>
                        }
                      />
                    </FormGroup>
                    <FormHelperText sx={{ ml: 0, color: "var(--page-text)", mt: 0.5 }}>
                      Разрешение браузера: {permissionText}
                    </FormHelperText>
                  </FormControl>

                  <FormControl
                    component="fieldset"
                    variant="standard"
                    disabled={!notificationsEnabled || pushBusy || pushInitializing}
                    sx={{ opacity: notificationsEnabled ? 1 : 0.6 }}
                  >
                    <FormGroup>
                      {topicKeys.map(key => (
                        <FormControlLabel
                          key={key}
                          control={
                            <Switch
                              checked={topicState[key]}
                              onChange={handleTopicToggle(key)}
                              disabled={!notificationsEnabled || pushBusy || pushInitializing}
                            />
                          }
                          label={
                            <span style={{ color: "var(--page-text)" }}>{NOTIFICATION_TOPIC_LABELS[key]}</span>
                          }
                        />
                      ))}
                    </FormGroup>
                    <FormHelperText sx={{ ml: 0, color: "var(--page-text)", mt: 0.5 }}>
                      Активные темы: {selectedTopicsDescription}
                    </FormHelperText>
                  </FormControl>

                  {notificationPermission === "denied" && (
                    <Alert severity="error" variant="outlined">
                      Разрешите уведомления в настройках браузера, чтобы получать оповещения.
                    </Alert>
                  )}

                  <Typography variant="body2" sx={{ color: "var(--page-text)" }}>
                    {notificationsEnabled
                      ? `Непрочитанные: ${unreadCount}.`
                      : "Уведомления сейчас отключены."}
                  </Typography>
                </Stack>
              )}
            </Box>
          </Stack>
        )}

        {tab === 1 && (
          <Box sx={{ width: "100%", maxWidth: { xs: "100%", sm: 640, md: 760, lg: 880 } }}>
            <List dense disablePadding>
              <ListItem
                divider
                secondaryAction={
                  <Stack direction="row" spacing={1}>
                    <Button size="small" variant="text" startIcon={<PhotoCameraIcon />} onClick={triggerAvatarPick} disabled={avatarBusy}>
                      Сменить
                    </Button>
                    <Button size="small" variant="text" color="error" startIcon={<DeleteOutlineIcon />} onClick={removeAvatar} disabled={avatarBusy}>
                      Удалить
                    </Button>
                  </Stack>
                }
              >
                <ListItemAvatar>
                  <Avatar
                    src={getAvatarSrc()}
                    alt={(user as any)?.full_name || "avatar"}
                    sx={{ width: 48, height: 48 }}
                    imgProps={{
                      onError: (e) => {
                        (e.currentTarget as HTMLImageElement).src = defaultAvatar;
                      }
                    }}
                  />
                </ListItemAvatar>
                <ListItemText primary="Фото профиля" secondary="PNG/JPG/WebP/AVIF/GIF, до 12 МБ" />
                <input
                  ref={avatarInputRef}
                  type="file"
                  accept="image/*"
                  hidden
                  onChange={(e) => {
                    const f = e.currentTarget.files?.[0];
                    if (f) uploadAvatar(f);
                  }}
                />
              </ListItem>

              <ListItem
                divider
                secondaryAction={
                  <Button size="small" variant="text" startIcon={<ImageIcon />} onClick={triggerCoverPick} disabled={coverBusy}>
                    Сменить
                  </Button>
                }
              >
                <ListItemAvatar sx={{ mr: 1.25 }}>
                  <Box
                    sx={{
                      width: 120,
                      height: 52,
                      borderRadius: 1.5,
                      border: "1px solid var(--glass-border)",
                      background: getCoverSrc() ? `url(${getCoverSrc()}) center/cover no-repeat` : "var(--card-bg)"
                    }}
                  />
                </ListItemAvatar>
                <ListItemText primary="Обложка профиля" secondary="Рекомендация: 1600×400+" />
                <input
                  ref={coverInputRef}
                  type="file"
                  accept="image/*"
                  hidden
                  onChange={(e) => {
                    const f = e.currentTarget.files?.[0];
                    if (f) uploadCover(f);
                  }}
                />
              </ListItem>

              <ListItem
                divider
                secondaryAction={
                  <Button size="small" variant="text" onClick={() => navigate({ pathname: "/profile", search: "?edit=1" })}>
                    Редактировать
                  </Button>
                }
              >
                <ListItemText primary="Профиль" secondary="Имя, контакты, соцсети" />
              </ListItem>
            </List>

            <Box sx={{ pt: 1.5, mt: 0.5, borderTop: "1px solid var(--glass-border)" }}>
              <List dense disablePadding>
                <ListItem>
                  <Button
                    size="small"
                    variant="text"
                    color="error"
                    startIcon={<LogoutIcon />}
                    onClick={() => setConfirmLogout(true)}
                    sx={{ px: 0 }}
                  >
                    Выйти
                  </Button>
                </ListItem>
              </List>
            </Box>
          </Box>
        )}

        {tab === 2 && (
          <Stack spacing={3}>
            <Stack spacing={2}>
              <Stack direction="row" alignItems="center" spacing={1}>
                <img src={spotifyLogo} alt="Spotify" width={22} height={22} style={{ display: "block", borderRadius: "50%" }} />
                <Typography variant="h6" sx={{ color: "var(--page-text)" }}>Spotify</Typography>
              </Stack>
              <Stack direction="row" alignItems="center" spacing={1.2} flexWrap="wrap">
                <Chip size="small" className="glass--chip" label={spotifyConnected ? "Подключено" : "Не подключено"} color={spotifyConnected ? "success" : "default"} variant="outlined" />
                {spotifyConnected && !!spotifyName && <Chip size="small" variant="outlined" label={spotifyName} />}
              </Stack>
              {!spotifyConnected ? (
                <Button variant="contained" onClick={connectSpotify} sx={{ alignSelf: "flex-start" }}>
                  Подключить Spotify
                </Button>
              ) : (
                <Button variant="outlined" color="error" onClick={disconnectSpotify} sx={{ alignSelf: "flex-start" }}>
                  Отключить Spotify
                </Button>
              )}
            </Stack>
          </Stack>
        )}
      </Paper>

      <Dialog open={confirmLogout} onClose={() => setConfirmLogout(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Выйти из аккаунта?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">Вы сможете войти снова. Данные не удаляются.</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmLogout(false)}>Отмена</Button>
          <Button color="error" onClick={() => { setConfirmLogout(false); logout(); }}>Выйти</Button>
        </DialogActions>
      </Dialog>

      <Snackbar open={!!snack} autoHideDuration={2600} onClose={() => setSnack(null)} anchorOrigin={{ vertical: "bottom", horizontal: "center" }}>
        <Alert onClose={() => setSnack(null)} severity={snack?.sev || "info"} variant="filled" sx={{ width: "100%" }}>
          {snack?.text}
        </Alert>
      </Snackbar>
    </Box>
  );
}