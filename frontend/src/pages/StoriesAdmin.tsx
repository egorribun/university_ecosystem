import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent } from "react"
import dayjs from "dayjs"
import utc from "dayjs/plugin/utc"
import { useTranslation } from "react-i18next"
import type { TFunction } from "i18next"
import { isAxiosError } from "axios"
import {
  Mail as EmailIcon,
  Camera as PhotoCamera,
  Trash2 as DeleteIcon,
  Check as CheckIcon,
  RefreshCw as RestartAltIcon,
  ChevronRight,
  Plus as AddIcon,
} from "lucide-react"

import Layout from "@/components/Layout"
import PageFadeIn from "@/components/PageFadeIn"
import SmartImage from "@/components/SmartImage"
import { useAuth } from "@/contexts/AuthContext"
import type { StoryItem } from "@/types/Story"
import { createStory, deleteStory, updateStory, uploadStoryCover } from "@/api/stories"
import apiClient from "@/api/client"
import { useLocaleFormatters } from "@/i18n/formatters"
import { sanitizeUrl } from "@/utils/media"
import { cn } from "@/utils/cn"
import {
  Alert,
  Button,
  CircularProgress,
  TextField,
  SectionCard,
  Divider,
} from "@/components/settings"
import { Badge, Card } from "@/components/ui"

dayjs.extend(utc)

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

function formatTimeLeft(expiresAt: string, now: dayjs.Dayjs, t: TFunction<"stories">) {
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
  if (isAxiosError(error)) {
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
  formatDate: (value: Date | string | number) => string
  onRefresh: () => void
}

function StoryAdminItem({ story, now, formatDate, onRefresh }: StoryAdminItemProps) {
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
    } catch (error: unknown) {
      setActionError(getErrorMessage(error, t("stories:errors.updateFailed")))
    } finally {
      setSavingTime(false)
    }
  }

  const handleCoverChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    if (!file.type.startsWith("image/")) {
      setActionError(t("stories:errors.invalidFileType"))
      return
    }
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
    } catch (error: unknown) {
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
    } catch (error: unknown) {
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
    } catch (error: unknown) {
      setActionError(getErrorMessage(error, t("stories:errors.deleteFailed")))
    } finally {
      setDeleting(false)
    }
  }

  return (
    <Card className="overflow-hidden border-glass-border bg-(--bg-surface)/40 shadow-glass backdrop-blur-md">
      <div className="px-6 py-5 border-b border-glass-border/30">
        <h3 className="text-lg font-extrabold text-(--text-primary)">{story.title}</h3>
        <p className="text-sm text-(--text-secondary) mt-0.5">{story.short_text}</p>
      </div>
      <div className="p-6">
        <div className="flex flex-col gap-6">
          <div className="flex flex-col md:flex-row gap-8">
            <div className="flex-1 flex flex-col gap-3">
              <div className="space-y-1">
                <p className="text-xs font-bold uppercase tracking-wider text-brand opacity-70">
                  {t("stories:list.details.published", { date: "" }).split(":")[0]}
                </p>
                <p className="text-sm font-medium text-(--text-primary)">
                  {formatDate(new Date(story.published_at))}
                </p>
              </div>
              <div className="space-y-1">
                <p className="text-xs font-bold uppercase tracking-wider text-brand opacity-70">
                  {t("stories:list.details.expires", { date: "" }).split(":")[0]}
                </p>
                <p className="text-sm font-medium text-(--text-primary)">
                  {formatDate(new Date(story.expires_at))}
                </p>
              </div>
              <Badge tone="primary" className="w-fit text-sm font-bold mt-2">
                {timeLeft}
              </Badge>
              {story.cta_url && (
                <div className="mt-2 p-3 rounded-xl bg-(--bg-surface)/20 border border-glass-border/20">
                  <p className="text-xs font-bold uppercase tracking-widest text-(--text-secondary) opacity-50 mb-1">
                    {t("stories:list.details.cta")}
                  </p>
                  <p className="text-xs font-mono break-all text-brand">{story.cta_url}</p>
                </div>
              )}
            </div>

            <div className="w-full md:w-56 flex flex-col items-center gap-4">
              <div className="relative w-full aspect-9/16 rounded-2xl overflow-hidden bg-(--bg-surface)/20 border border-glass-border shadow-inner group">
                {coverPreview ? (
                  <img
                    src={sanitizeUrl(coverPreview) ?? ""}
                    alt={t("stories:list.coverAlt", { title: story.title })}
                    className="w-full h-full object-cover"
                  />
                ) : story.cover_url ? (
                  <SmartImage
                    srcRaw={story.cover_url}
                    alt={story.title}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center p-6 text-center bg-linear-to-r from-blue-500 to-indigo-600 transition-all duration-300">
                    <p className="text-xs font-medium text-(--text-secondary) opacity-60">
                      {t("stories:list.noCover")}
                    </p>
                  </div>
                )}
              </div>

              <div className="w-full space-y-2">
                <div className="flex gap-2 w-full">
                  <Button
                    as="label"
                    variant="outline"
                    size="sm"
                    className="flex-1"
                    startIcon={<PhotoCamera className="h-4 w-4" />}
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
                      variant="outline"
                      size="sm"
                      onClick={handleCoverReset}
                      startIcon={<RestartAltIcon className="h-4 w-4" />}
                      className="text-(--text-secondary)"
                    />
                  )}
                </div>
                <Button
                  variant="solid"
                  size="sm"
                  className="w-full"
                  disabled={!coverFile || updatingCover}
                  onClick={handleCoverUpdate}
                  loading={updatingCover}
                >
                  {t("stories:list.actions.updateCover")}
                </Button>
              </div>
            </div>
          </div>

          <Divider className="opacity-10" />

          <div className="flex flex-col gap-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <TextField
                label={t("stories:form.publishedAt")}
                type="datetime-local"
                value={publishedAt}
                onChange={(event) => setPublishedAt(event.target.value)}
              />
              <TextField
                label={t("stories:form.expiresAt")}
                type="datetime-local"
                value={expiresAt}
                onChange={(event) => setExpiresAt(event.target.value)}
              />
            </div>
            <div className="flex flex-wrap gap-3 mt-2">
              <Button
                variant="solid"
                onClick={handleTimeSave}
                disabled={savingTime}
                loading={savingTime}
              >
                {t("stories:list.actions.updateTimer")}
              </Button>
              <Button
                variant="outline"
                className="text-(--warning-text) border-(--warning-text)/30 hover:bg-(--warning-text)/10"
                onClick={handleUnpublish}
                disabled={unpublishing}
                loading={unpublishing}
              >
                {t("stories:list.actions.unpublish")}
              </Button>
              <Button
                variant="outline"
                className="text-(--error-text) border-(--error-text)/30 hover:bg-(--error-text)/10 ml-auto"
                onClick={handleDelete}
                disabled={deleting}
                loading={deleting}
                startIcon={<DeleteIcon className="h-4 w-4" />}
              >
                {t("common:buttons.delete")}
              </Button>
            </div>
          </div>
          {actionError && (
            <Alert severity="error" className="shadow-sm">
              {actionError}
            </Alert>
          )}
        </div>
      </div>
    </Card>
  )
}

export default function StoriesAdmin() {
  const { user } = useAuth()
  const { t } = useTranslation(["stories", "common"])
  const { formatDate } = useLocaleFormatters()
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
      const response = await apiClient.get<StoryItem[]>("/stories")
      const data = Array.isArray(response.data) ? response.data : []
      setStories(data)
      setListError(null)
    } catch (error: unknown) {
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
    } catch (error: unknown) {
      setFormError(getErrorMessage(error, t("stories:errors.createFailed")))
    } finally {
      setSubmitting(false)
    }
  }

  if (!isAdmin) {
    return (
      <Layout>
        <PageFadeIn>
          <div className="flex min-h-[70vh] items-center justify-center px-4">
            <h2 className="text-2xl font-bold opacity-40">{t("stories:notAuthorized")}</h2>
          </div>
        </PageFadeIn>
      </Layout>
    )
  }

  return (
    <Layout>
      <PageFadeIn>
        <div className="mx-auto max-w-[1100px] px-4 py-8 md:py-12">
          <div className="mb-10 flex items-center gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-brand/10 text-brand">
              <RestartAltIcon className="h-7 w-7" />
            </div>
            <h1 className="text-3xl font-extrabold tracking-tight text-(--text-primary)">
              {t("stories:pageTitle")}
            </h1>
          </div>

          <SectionCard className="mb-12">
            <div className="px-6 py-5 border-b border-glass-border/30">
              <h2 className="text-lg font-bold text-(--text-primary)">{t("stories:form.title")}</h2>
              <p className="text-sm text-(--text-secondary) mt-0.5">{t("stories:form.subtitle")}</p>
            </div>
            <div className="p-6">
              <div className="flex flex-col gap-6">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <TextField
                    label={t("stories:form.titleRu")}
                    value={formState.titleRu}
                    onChange={(event) => handleFormChange("titleRu")(event.target.value)}
                  />
                  <TextField
                    label={t("stories:form.titleEn")}
                    value={formState.titleEn}
                    onChange={(event) => handleFormChange("titleEn")(event.target.value)}
                  />
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <TextField
                    label={t("stories:form.shortTextRu")}
                    value={formState.shortTextRu}
                    onChange={(event) => handleFormChange("shortTextRu")(event.target.value)}
                    multiline
                    rows={2}
                  />
                  <TextField
                    label={t("stories:form.shortTextEn")}
                    value={formState.shortTextEn}
                    onChange={(event) => handleFormChange("shortTextEn")(event.target.value)}
                    multiline
                    rows={2}
                  />
                </div>
                <TextField
                  label={t("stories:form.ctaUrl")}
                  value={formState.ctaUrl}
                  onChange={(event) => handleFormChange("ctaUrl")(event.target.value)}
                />
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <TextField
                    label={t("stories:form.publishedAt")}
                    type="datetime-local"
                    value={formState.publishedAt}
                    onChange={(event) => handleFormChange("publishedAt")(event.target.value)}
                  />
                  <TextField
                    label={t("stories:form.expiresAt")}
                    type="datetime-local"
                    value={formState.expiresAt}
                    onChange={(event) => handleFormChange("expiresAt")(event.target.value)}
                  />
                </div>

                <div className="flex flex-col gap-4 py-2">
                  <div className="flex items-center gap-3">
                    <Button
                      as="label"
                      variant="outline"
                      startIcon={<PhotoCamera className="h-4 w-4" />}
                    >
                      {coverFile
                        ? t("common:buttons.changePhoto")
                        : t("common:buttons.uploadPhoto")}
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
                        variant="ghost"
                        onClick={resetCoverOnly}
                        startIcon={<RestartAltIcon className="h-4 w-4" />}
                        className="text-(--text-secondary)"
                      >
                        {t("stories:form.resetCover")}
                      </Button>
                    )}
                  </div>

                  {coverPreview && (
                    <div className="relative w-full sm:w-80 aspect-9/16 rounded-3xl overflow-hidden border border-glass-border shadow-2xl mt-2 group mx-auto md:mx-0">
                      <SmartImage
                        srcRaw={coverPreview || ""}
                        alt={t("stories:form.previewAlt")}
                        className="w-full h-full object-cover"
                      />
                      <div className="absolute inset-x-0 bottom-0 p-6 bg-linear-to-t from-black/80 to-transparent">
                        <h4 className="text-white font-bold text-lg">
                          {formState.titleRu || "Title"}
                        </h4>
                        <p className="text-white/70 text-sm line-clamp-2">
                          {formState.shortTextRu || "Text"}
                        </p>
                      </div>
                    </div>
                  )}
                </div>

                <div className="flex flex-wrap gap-3 pt-4 border-t border-glass-border/20">
                  <Button
                    onClick={handleSubmit}
                    disabled={submitting}
                    loading={submitting}
                    startIcon={<CheckIcon className="h-4 w-4" />}
                  >
                    {t("common:buttons.submit")}
                  </Button>
                  <Button
                    onClick={resetForm}
                    variant="ghost"
                    startIcon={<RestartAltIcon className="h-4 w-4" />}
                  >
                    {t("common:buttons.reset")}
                  </Button>
                </div>

                {formError && <Alert severity="error">{formError}</Alert>}
                {formSuccess && <Alert severity="success">{formSuccess}</Alert>}
              </div>
            </div>
          </SectionCard>

          <div className="space-y-6">
            <div className="flex items-center justify-between px-2">
              <h2 className="text-2xl font-extrabold text-(--text-primary) flex items-center gap-3">
                {t("stories:list.title")}
                <span className="px-2 py-0.5 rounded-full bg-brand/10 border border-brand/20 text-xs font-bold tabular-nums text-brand">
                  {stories.length}
                </span>
              </h2>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => void fetchStories()}
                startIcon={<RestartAltIcon className={cn("h-4 w-4", loading && "animate-spin")} />}
              >
                {t("common:buttons.refresh")}
              </Button>
            </div>

            {listError && (
              <Alert severity="error" className="shadow-sm">
                {listError}
              </Alert>
            )}

            {loading && stories.length === 0 ? (
              <div className="flex justify-center py-20">
                <CircularProgress size={40} />
              </div>
            ) : stories.length === 0 ? (
              <div className="text-center py-20 bg-(--bg-surface)/10 rounded-3xl border border-dashed border-glass-border/30">
                <p className="text-(--text-secondary) italic">{t("stories:list.empty")}</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {stories.map((story) => (
                  <StoryAdminItem
                    key={story.id}
                    story={story}
                    now={now}
                    formatDate={(value) => formatDate(value, { preset: "datetime" })}
                    onRefresh={() => void fetchStories()}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </PageFadeIn>
    </Layout>
  )
}
