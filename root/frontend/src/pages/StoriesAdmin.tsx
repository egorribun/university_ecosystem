import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent } from "react"
import dayjs from "dayjs"
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  CircularProgress,
  Divider,
  Stack,
  TextField,
  Typography,
} from "@mui/material"
import PhotoCamera from "@mui/icons-material/PhotoCamera"
import DeleteIcon from "@mui/icons-material/Delete"
import RestartAltIcon from "@mui/icons-material/RestartAlt"
import Layout from "@/components/Layout"
import PageFadeIn from "@/components/PageFadeIn"
import SmartImage from "@/components/SmartImage"
import { useAuth } from "@/contexts/AuthContext"
import { useLanguage } from "@/contexts/LanguageContext"
import type { StoryItem } from "@/types/Story"
import { createStory, deleteStory, updateStory, uploadStoryCover } from "@/api/stories"
import axios from "@/api/client"
import { useTranslation } from "react-i18next"

function formatInputDate(value: string | dayjs.Dayjs) {
  const parsed = typeof value === "string" ? dayjs(value) : value
  if (!parsed.isValid()) return ""
  return parsed.local().second(0).millisecond(0).format("YYYY-MM-DDTHH:mm")
}

function toIso(date: string) {
  const parsed = dayjs(date)
  if (!parsed.isValid()) return null
  return parsed.toDate().toISOString()
}

function formatTimeLeft(
  expiresAt: string,
  now: dayjs.Dayjs,
  t: ReturnType<typeof useTranslation>["t"]
) {
  const expires = dayjs(expiresAt)
  if (!expires.isValid()) return t("stories:list.timeLeft.unknown")
  const diffSeconds = Math.floor(expires.diff(now, "second"))
  if (diffSeconds <= 0) return t("stories:list.timeLeft.expired")
  const minutes = Math.floor(diffSeconds / 60)
  const days = Math.floor(minutes / (60 * 24))
  const hours = Math.floor((minutes - days * 24 * 60) / 60)
  const mins = minutes - days * 24 * 60 - hours * 60
  const parts: string[] = []
  if (days) parts.push(t("stories:list.timeLeft.days", { count: days }))
  if (hours) parts.push(t("stories:list.timeLeft.hours", { count: hours }))
  if (mins || parts.length === 0) parts.push(t("stories:list.timeLeft.minutes", { count: mins }))
  return t("stories:list.timeLeft.label", { time: parts.join(" ") })
}

function getErrorMessage(error: unknown, fallback: string) {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data as { detail?: unknown } | undefined
    if (detail) {
      if (typeof detail === "string") return detail
      if (typeof detail.detail === "string") return detail.detail
    }
  }
  if (error instanceof Error && error.message) return error.message
  return fallback
}

type StoryFormState = {
  titleRu: string
  titleEn: string
  shortTextRu: string
  shortTextEn: string
  ctaUrl: string
  publishedAt: string
  expiresAt: string
}

const createInitialFormState = (): StoryFormState => ({
  titleRu: "",
  titleEn: "",
  shortTextRu: "",
  shortTextEn: "",
  ctaUrl: "",
  publishedAt: formatInputDate(dayjs()),
  expiresAt: formatInputDate(dayjs().add(1, "day")),
})

type StoryAdminItemProps = {
  story: StoryItem
  now: dayjs.Dayjs
  locale: string
  onRefresh: () => void
}

function StoryAdminItem({ story, now, locale, onRefresh }: StoryAdminItemProps) {
  const { t } = useTranslation(["stories", "common"])
  const [publishedAt, setPublishedAt] = useState(() => formatInputDate(story.published_at))
  const [expiresAt, setExpiresAt] = useState(() => formatInputDate(story.expires_at))
  const [actionError, setActionError] = useState<string | null>(null)
  const [savingTime, setSavingTime] = useState(false)
  const [coverFile, setCoverFile] = useState<File | null>(null)
  const [coverPreview, setCoverPreview] = useState<string | null>(null)
  const [updatingCover, setUpdatingCover] = useState(false)
  const [unpublishing, setUnpublishing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    setPublishedAt(formatInputDate(story.published_at))
    setExpiresAt(formatInputDate(story.expires_at))
  }, [story.published_at, story.expires_at])

  useEffect(() => {
    return () => {
      if (coverPreview) URL.revokeObjectURL(coverPreview)
    }
  }, [coverPreview])

  const dateFormatter = useMemo(
    () =>
      new Intl.DateTimeFormat(locale, {
        dateStyle: "medium",
        timeStyle: "short",
      }),
    [locale]
  )

  const timeLeft = useMemo(
    () => formatTimeLeft(story.expires_at, now, t),
    [story.expires_at, now, t]
  )

  const handleTimeSave = async () => {
    setActionError(null)
    const publishIso = toIso(publishedAt)
    const expiresIso = toIso(expiresAt)
    if (!publishIso || !expiresIso) {
      setActionError(t("stories:errors.invalidDate"))
      return
    }
    if (!dayjs(expiresIso).isAfter(dayjs(publishIso))) {
      setActionError(t("stories:errors.expirationAfterPublish"))
      return
    }
    setSavingTime(true)
    try {
      await updateStory(story.id, {
        published_at: publishIso,
        expires_at: expiresIso,
      })
      onRefresh()
    } catch (error) {
      setActionError(getErrorMessage(error, t("stories:errors.updateFailed")))
    } finally {
      setSavingTime(false)
    }
  }

  const handleCoverChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    setCoverFile(file)
    if (coverPreview) URL.revokeObjectURL(coverPreview)
    setCoverPreview(URL.createObjectURL(file))
  }

  const handleCoverReset = () => {
    setCoverFile(null)
    if (coverPreview) {
      URL.revokeObjectURL(coverPreview)
      setCoverPreview(null)
    }
    if (fileInputRef.current) fileInputRef.current.value = ""
  }

  const handleCoverUpdate = async () => {
    if (!coverFile) return
    setActionError(null)
    setUpdatingCover(true)
    try {
      const uploaded = await uploadStoryCover(coverFile)
      const url = uploaded.data?.url ?? ""
      await updateStory(story.id, { cover_url: url })
      handleCoverReset()
      onRefresh()
    } catch (error) {
      setActionError(getErrorMessage(error, t("stories:errors.coverUpdateFailed")))
    } finally {
      setUpdatingCover(false)
    }
  }

  const handleUnpublish = async () => {
    setActionError(null)
    setUnpublishing(true)
    try {
      await updateStory(story.id, { is_active: false })
      onRefresh()
    } catch (error) {
      setActionError(getErrorMessage(error, t("stories:errors.unpublishFailed")))
    } finally {
      setUnpublishing(false)
    }
  }

  const handleDelete = async () => {
    if (!window.confirm(t("stories:list.confirmDelete"))) return
    setActionError(null)
    setDeleting(true)
    try {
      await deleteStory(story.id)
      onRefresh()
    } catch (error) {
      setActionError(getErrorMessage(error, t("stories:errors.deleteFailed")))
    } finally {
      setDeleting(false)
    }
  }

  return (
    <Card variant="outlined" sx={{ borderRadius: 3 }}>
      <CardHeader
        title={story.title}
        subheader={story.short_text}
        sx={{
          alignItems: "flex-start",
          "& .MuiCardHeader-title": { fontSize: "1.1rem", fontWeight: 700 },
          "& .MuiCardHeader-subheader": { fontSize: "0.95rem" },
        }}
      />
      <Divider />
      <CardContent>
        <Stack spacing={2}>
          <Stack direction={{ xs: "column", md: "row" }} spacing={3} alignItems="stretch">
            <Box flex={1} minWidth={0}>
              <Typography variant="body2" color="text.secondary">
                {t("stories:list.details.published", {
                  date: dateFormatter.format(new Date(story.published_at)),
                })}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {t("stories:list.details.expires", {
                  date: dateFormatter.format(new Date(story.expires_at)),
                })}
              </Typography>
              <Typography variant="body1" fontWeight={600} color="primary.main" mt={1}>
                {timeLeft}
              </Typography>
              {story.cta_url && (
                <Typography
                  variant="body2"
                  color="text.secondary"
                  mt={1}
                  sx={{ wordBreak: "break-all" }}
                >
                  {t("stories:list.details.cta")}: {story.cta_url}
                </Typography>
              )}
            </Box>
            <Box
              sx={{
                width: { xs: "100%", md: 220 },
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 1.5,
              }}
            >
              <Box
                sx={{
                  width: "100%",
                  borderRadius: 3,
                  overflow: "hidden",
                  background: "rgba(0,0,0,0.08)",
                  aspectRatio: "9 / 16",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                {coverPreview ? (
                  <img
                    src={coverPreview}
                    alt={t("stories:list.coverAlt", { title: story.title })}
                    style={{ width: "100%", height: "100%", objectFit: "cover" }}
                  />
                ) : story.cover_url ? (
                  <SmartImage
                    srcRaw={story.cover_url}
                    alt={story.title}
                    style={{ width: "100%", height: "100%" }}
                  />
                ) : (
                  <Typography variant="body2" color="text.secondary" textAlign="center" px={2}>
                    {t("stories:list.noCover")}
                  </Typography>
                )}
              </Box>
              <Stack direction="row" spacing={1} width="100%" justifyContent="center">
                <Button
                  component="label"
                  variant="outlined"
                  startIcon={<PhotoCamera />}
                  sx={{ flex: 1 }}
                >
                  {coverFile
                    ? t("common:buttons.changePhoto")
                    : t("stories:list.actions.pickCover")}
                  <input
                    type="file"
                    accept="image/*"
                    hidden
                    onChange={handleCoverChange}
                    ref={fileInputRef}
                  />
                </Button>
                {coverFile && (
                  <Button
                    variant="outlined"
                    color="secondary"
                    onClick={handleCoverReset}
                    startIcon={<RestartAltIcon />}
                  >
                    {t("stories:list.actions.clearCover")}
                  </Button>
                )}
              </Stack>
              <Button
                variant="contained"
                disabled={!coverFile || updatingCover}
                onClick={handleCoverUpdate}
                fullWidth
              >
                {updatingCover
                  ? t("common:statuses.uploading")
                  : t("stories:list.actions.updateCover")}
              </Button>
            </Box>
          </Stack>

          <Divider flexItem />

          <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
            <TextField
              label={t("stories:form.publishedAt")}
              type="datetime-local"
              value={publishedAt}
              onChange={(e) => setPublishedAt(e.target.value)}
              InputLabelProps={{ shrink: true }}
              fullWidth
            />
            <TextField
              label={t("stories:form.expiresAt")}
              type="datetime-local"
              value={expiresAt}
              onChange={(e) => setExpiresAt(e.target.value)}
              InputLabelProps={{ shrink: true }}
              fullWidth
            />
          </Stack>
          <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
            <Button variant="contained" onClick={handleTimeSave} disabled={savingTime}>
              {savingTime ? t("common:statuses.loading") : t("stories:list.actions.updateTimer")}
            </Button>
            <Button
              variant="outlined"
              color="warning"
              onClick={handleUnpublish}
              disabled={unpublishing}
            >
              {unpublishing ? t("common:statuses.loading") : t("stories:list.actions.unpublish")}
            </Button>
            <Button
              variant="outlined"
              color="error"
              onClick={handleDelete}
              startIcon={<DeleteIcon />}
              disabled={deleting}
            >
              {deleting ? t("common:statuses.loading") : t("common:buttons.delete")}
            </Button>
          </Stack>
          {actionError && <Alert severity="error">{actionError}</Alert>}
        </Stack>
      </CardContent>
    </Card>
  )
}

export default function StoriesAdmin() {
  const { user } = useAuth()
  const { language } = useLanguage()
  const { t } = useTranslation(["stories", "common"])
  const isAdmin = user?.role === "admin"
  const [stories, setStories] = useState<StoryItem[]>([])
  const [loading, setLoading] = useState(false)
  const [formState, setFormState] = useState<StoryFormState>(() => createInitialFormState())
  const [coverFile, setCoverFile] = useState<File | null>(null)
  const [coverPreview, setCoverPreview] = useState<string | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const [formSuccess, setFormSuccess] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const [now, setNow] = useState(dayjs())
  const [listError, setListError] = useState<string | null>(null)

  useEffect(() => {
    const id = window.setInterval(() => setNow(dayjs()), 60000)
    return () => window.clearInterval(id)
  }, [])

  useEffect(() => {
    return () => {
      if (coverPreview) URL.revokeObjectURL(coverPreview)
    }
  }, [coverPreview])

  const fetchStories = useCallback(async () => {
    setLoading(true)
    setListError(null)
    try {
      const res = await axios.get<StoryItem[]>("/stories")
      const data = Array.isArray(res.data) ? res.data : []
      setStories(data)
      setListError(null)
    } catch (error) {
      setListError(getErrorMessage(error, t("stories:errors.loadFailed")))
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => {
    if (!isAdmin) return
    void fetchStories()
  }, [fetchStories, isAdmin])

  const handleFormChange = (field: keyof StoryFormState) => (value: string) => {
    setFormState((prev) => ({ ...prev, [field]: value }))
  }

  const handleCoverChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    setCoverFile(file)
    if (coverPreview) URL.revokeObjectURL(coverPreview)
    setCoverPreview(URL.createObjectURL(file))
  }

  const resetCoverOnly = () => {
    setCoverFile(null)
    if (coverPreview) {
      URL.revokeObjectURL(coverPreview)
      setCoverPreview(null)
    }
    if (fileInputRef.current) fileInputRef.current.value = ""
  }

  const resetForm = () => {
    setFormState(createInitialFormState())
    resetCoverOnly()
  }

  const handleSubmit = async () => {
    setFormError(null)
    setFormSuccess(null)
    if (!formState.titleRu.trim() || !formState.shortTextRu.trim()) {
      setFormError(t("stories:errors.required"))
      return
    }
    const publishIso = toIso(formState.publishedAt)
    const expiresIso = toIso(formState.expiresAt)
    if (!publishIso || !expiresIso) {
      setFormError(t("stories:errors.invalidDate"))
      return
    }
    if (!dayjs(expiresIso).isAfter(dayjs(publishIso))) {
      setFormError(t("stories:errors.expirationAfterPublish"))
      return
    }
    setSubmitting(true)
    try {
      let coverUrl: string | null = null
      if (coverFile) {
        const uploaded = await uploadStoryCover(coverFile)
        coverUrl = uploaded.data?.url ?? null
      }
      await createStory({
        title: formState.titleRu,
        short_text: formState.shortTextRu,
        ...(formState.titleEn.trim() ? { title_en: formState.titleEn.trim() } : {}),
        ...(formState.shortTextEn.trim() ? { short_text_en: formState.shortTextEn.trim() } : {}),
        ...(formState.ctaUrl.trim() ? { cta_url: formState.ctaUrl.trim() } : {}),
        published_at: publishIso,
        expires_at: expiresIso,
        ...(coverUrl ? { cover_url: coverUrl } : {}),
        is_active: true,
      })
      resetForm()
      setFormSuccess(t("stories:form.success"))
      void fetchStories()
    } catch (error) {
      setFormError(getErrorMessage(error, t("stories:errors.createFailed")))
    } finally {
      setSubmitting(false)
    }
  }

  if (!isAdmin) {
    return (
      <Layout>
        <PageFadeIn>
          <Box
            sx={{
              width: "100%",
              minHeight: "70vh",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              px: 2,
            }}
          >
            <Typography variant="h5" textAlign="center">
              {t("stories:notAuthorized")}
            </Typography>
          </Box>
        </PageFadeIn>
      </Layout>
    )
  }

  return (
    <Layout>
      <PageFadeIn>
        <Box
          sx={{
            width: "100%",
            maxWidth: 1100,
            mx: "auto",
            py: { xs: 4, md: 6 },
            px: { xs: 2, sm: 3, md: 4 },
            color: "var(--page-text)",
          }}
        >
          <Typography variant="h4" component="h1" fontWeight={700} mb={3} color="primary.main">
            {t("stories:pageTitle")}
          </Typography>

          <Card variant="outlined" sx={{ borderRadius: 3, mb: 4 }}>
            <CardHeader
              title={t("stories:form.title")}
              subheader={t("stories:form.subtitle")}
              sx={{ "& .MuiCardHeader-title": { fontWeight: 700, fontSize: "1.2rem" } }}
            />
            <Divider />
            <CardContent>
              <Stack spacing={2}>
                <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                  <TextField
                    label={t("stories:form.titleRu")}
                    value={formState.titleRu}
                    onChange={(e) => handleFormChange("titleRu")(e.target.value)}
                    fullWidth
                  />
                  <TextField
                    label={t("stories:form.titleEn")}
                    value={formState.titleEn}
                    onChange={(e) => handleFormChange("titleEn")(e.target.value)}
                    fullWidth
                  />
                </Stack>
                <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                  <TextField
                    label={t("stories:form.shortTextRu")}
                    value={formState.shortTextRu}
                    onChange={(e) => handleFormChange("shortTextRu")(e.target.value)}
                    fullWidth
                    multiline
                    minRows={2}
                  />
                  <TextField
                    label={t("stories:form.shortTextEn")}
                    value={formState.shortTextEn}
                    onChange={(e) => handleFormChange("shortTextEn")(e.target.value)}
                    fullWidth
                    multiline
                    minRows={2}
                  />
                </Stack>
                <TextField
                  label={t("stories:form.ctaUrl")}
                  value={formState.ctaUrl}
                  onChange={(e) => handleFormChange("ctaUrl")(e.target.value)}
                  fullWidth
                />
                <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                  <TextField
                    label={t("stories:form.publishedAt")}
                    type="datetime-local"
                    value={formState.publishedAt}
                    onChange={(e) => handleFormChange("publishedAt")(e.target.value)}
                    InputLabelProps={{ shrink: true }}
                    fullWidth
                  />
                  <TextField
                    label={t("stories:form.expiresAt")}
                    type="datetime-local"
                    value={formState.expiresAt}
                    onChange={(e) => handleFormChange("expiresAt")(e.target.value)}
                    InputLabelProps={{ shrink: true }}
                    fullWidth
                  />
                </Stack>
                <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems="center">
                  <Button
                    component="label"
                    variant="outlined"
                    startIcon={<PhotoCamera />}
                    sx={{ alignSelf: "stretch" }}
                  >
                    {coverFile ? t("common:buttons.changePhoto") : t("common:buttons.uploadPhoto")}
                    <input
                      type="file"
                      accept="image/*"
                      hidden
                      onChange={handleCoverChange}
                      ref={fileInputRef}
                    />
                  </Button>
                  {coverFile && (
                    <Button
                      variant="outlined"
                      color="secondary"
                      onClick={resetCoverOnly}
                      startIcon={<RestartAltIcon />}
                    >
                      {t("stories:form.resetCover")}
                    </Button>
                  )}
                </Stack>
                {coverPreview && (
                  <Box
                    sx={{
                      width: "100%",
                      display: "flex",
                      justifyContent: "center",
                    }}
                  >
                    <Box
                      sx={{
                        width: { xs: "100%", sm: 320 },
                        borderRadius: 3,
                        overflow: "hidden",
                        boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
                      }}
                    >
                      <img
                        src={coverPreview}
                        alt={t("stories:form.previewAlt")}
                        style={{ width: "100%", display: "block" }}
                      />
                    </Box>
                  </Box>
                )}
                <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                  <Button variant="contained" onClick={handleSubmit} disabled={submitting}>
                    {submitting ? t("common:statuses.publishing") : t("stories:form.submit")}
                  </Button>
                  <Button variant="outlined" onClick={resetForm} startIcon={<RestartAltIcon />}>
                    {t("common:buttons.reset")}
                  </Button>
                </Stack>
                {formError && <Alert severity="error">{formError}</Alert>}
                {formSuccess && <Alert severity="success">{formSuccess}</Alert>}
              </Stack>
            </CardContent>
          </Card>

          <Box>
            <Stack direction="row" alignItems="center" spacing={2} mb={2}>
              <Typography variant="h5" component="h2" fontWeight={600}>
                {t("stories:list.title")}
              </Typography>
              <Button variant="text" onClick={() => void fetchStories()}>
                {t("common:buttons.refresh")}
              </Button>
            </Stack>
            {listError && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {listError}
              </Alert>
            )}
            {loading ? (
              <Box display="flex" justifyContent="center" py={6}>
                <CircularProgress size={36} />
              </Box>
            ) : stories.length === 0 ? (
              <Typography color="text.secondary">{t("stories:list.empty")}</Typography>
            ) : (
              <Stack spacing={3}>
                {stories.map((story) => (
                  <StoryAdminItem
                    key={story.id}
                    story={story}
                    now={now}
                    locale={language === "ru" ? "ru-RU" : "en-US"}
                    onRefresh={() => void fetchStories()}
                  />
                ))}
              </Stack>
            )}
          </Box>
        </Box>
      </PageFadeIn>
    </Layout>
  )
}
