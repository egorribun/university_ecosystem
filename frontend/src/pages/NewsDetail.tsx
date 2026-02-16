import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import {
  ArrowLeft as ArrowBackIcon,
  Edit2 as EditIcon,
  Trash2 as DeleteIcon,
  Camera as PhotoCamera,
  Share2 as IosShareIcon,
  Copy as ContentCopyIcon,
  Heart as FavoriteIcon,
} from "lucide-react"
import {
  Alert,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Snackbar,
} from "@/components/settings"
import { useNewsInteraction } from "@/hooks/useNewsInteraction"
import { useShare } from "@/hooks/useShare"
import dayjs from "dayjs"
import utc from "dayjs/plugin/utc"
import timezone from "dayjs/plugin/timezone"
import { deleteNews, fetchNewsItem, updateNews, uploadNewsImage, type NewsItem } from "@/api/news"
import Layout from "@/components/Layout"
import { SEO } from "@/components/SEO"
import SmartImage from "@/components/SmartImage"
import { Button, Input, Textarea, ConfirmDialog } from "@/components/ui"
import { NewsComments } from "@/components/news/NewsComments"
import { useAuth } from "@/contexts/AuthContext"
import { useLanguage } from "@/contexts/LanguageContext"
import { useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"

dayjs.extend(utc)
dayjs.extend(timezone)

const iconButtonClass =
  "inline-flex h-10 w-10 items-center justify-center rounded-full border border-(--glass-border) bg-(--bg-surface)/(--opacity-hover) text-(--text-secondary) shadow-sm transition hover:bg-(--bg-surface) hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--brand-main)"

type FieldProps = {
  label: ReactNode
  htmlFor: string
  children: ReactNode
  required?: boolean
}

function Field({ label, htmlFor, children, required = false }: FieldProps) {
  return (
    <div className="flex flex-col gap-2">
      <label
        htmlFor={htmlFor}
        className="text-sm font-semibold tracking-wide text-(--text-secondary)/(--opacity-hover)"
      >
        {label}
        {required ? <span className="ml-1 text-(--error-text)">*</span> : null}
      </label>
      {children}
    </div>
  )
}

async function fetchNews(id: string): Promise<NewsItem> {
  const response = await fetchNewsItem(id)
  if (response.status === 304) {
    throw new Error("Not modified")
  }
  return response.data
}

const getMoscowDate = (dateStr: string) => {
  let parsed = dayjs(dateStr)
  if (!/([Zz]|[+-]\d\d:?\d\d)$/.test(dateStr)) parsed = dayjs.utc(dateStr)
  return parsed.tz("Europe/Moscow").format("DD.MM.YYYY HH:mm")
}

export default function NewsDetail() {
  const { id = "" } = useParams()
  const navigate = useNavigate()
  const { user } = useAuth()
  const { t } = useTranslation(["news", "common"])
  const { language } = useLanguage()
  const queryClient = useQueryClient()

  const [editOpen, setEditOpen] = useState(false)
  const [editData, setEditData] = useState({
    title: "",
    content: "",
    title_en: "",
    content_en: "",
    image_url: "",
  })
  const [saving, setSaving] = useState(false)
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [newImage, setNewImage] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [snackbar, setSnackbar] = useState("")
  const [heroRatio, setHeroRatio] = useState<number | null>(null)
  const imageInputRef = useRef<HTMLInputElement>(null)
  const editTitleRef = useRef<HTMLInputElement>(null)

  const { data: newsItem } = useQuery<NewsItem>({ queryKey: ["news", id, language] })

  const {
    sharing,
    shareDialogOpen,
    setShareDialogOpen,
    copyingLink,
    copiedLink,
    shareOptions,
    handleShare,
    handleCopyLink,
  } = useShare({
    title: newsItem?.title || "",
    onNotify: (msg) => setSnackbar(msg),
    translations: {
      shareSuccess: t("news:notifications.shareSuccess"),
      shareError: t("news:notifications.shareError"),
      linkCopied: t("news:notifications.linkCopied"),
      pageTitle: t("news:pageTitle"),
      telegram: t("news:shareDialog.options.telegram"),
      whatsapp: t("news:shareDialog.options.whatsapp"),
      email: t("news:shareDialog.options.email"),
    },
  })

  const { interactions, toggleLike, addComment, isCommenting, updateComment, deleteComment } =
    useNewsInteraction(id, {
      initialData: newsItem
        ? {
            likes_count: newsItem.likes_count,
            comments_count: newsItem.comments_count,
            is_liked: newsItem.is_liked,
          }
        : undefined,
    })
  const isLiked = interactions?.is_liked ?? false
  const likesCount = interactions?.likes_count ?? 0
  const comments = interactions?.comments ?? []

  const handleHeroLoad = useCallback<React.ReactEventHandler<HTMLImageElement>>((event) => {
    const img = event.currentTarget
    const width = img.naturalWidth || 0
    const height = img.naturalHeight || 0
    if (!width || !height) return

    setHeroRatio(width / height)
  }, [])

  const heroFrame = useMemo(() => {
    if (!heroRatio || !Number.isFinite(heroRatio) || heroRatio <= 0) {
      return {
        container: "h-(--h-hero-sm) min-h-80 max-h-(--layout-max-modal)",
        image: "object-cover object-[50%_40%]",
        backdrop: "bg-black/(--opacity-dim)",
      }
    }

    const ratio = Math.min(Math.max(heroRatio, 0.35), 4)

    if (ratio < 0.82) {
      return {
        container: "min-h-(--min-h-hero-lg) max-h-(--h-hero-max-portrait) aspect-3/4",
        image: "object-contain object-center",
        backdrop: "bg-black/(--opacity-soft)",
      }
    }

    if (ratio < 1.18) {
      return {
        container: "min-h-(--min-h-hero-md) max-h-(--h-hero-max-square) aspect-5/4",
        image: "object-cover object-[50%_38%]",
        backdrop: "bg-(--bg-surface)/(--opacity-dim)",
      }
    }

    if (ratio > 2.6) {
      return {
        container: "min-h-(--min-h-hero-xs) max-h-(--h-hero-md) aspect-21/9",
        image: "object-cover object-[50%_46%]",
        backdrop: "bg-black/(--opacity-dim)",
      }
    }

    return {
      container: "min-h-(--min-h-hero-sm) max-h-(--h-hero-max-landscape) aspect-video",
      image: "object-cover object-[50%_40%]",
      backdrop: "bg-(--bg-surface)/(--opacity-dim)",
    }
  }, [heroRatio])

  const query = useQuery<NewsItem, Error>({
    queryKey: ["news", id, language],
    queryFn: () => fetchNews(id),
    enabled: !!id,
    staleTime: 60000,
    retry: 1,
  })

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl)
    }
  }, [previewUrl])

  useEffect(() => {
    if (!snackbar) return
    const timeout = window.setTimeout(() => setSnackbar(""), 2400)
    return () => window.clearTimeout(timeout)
  }, [snackbar])

  const resetPreview = () => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl)
      setPreviewUrl(null)
    }
    if (imageInputRef.current) imageInputRef.current.value = ""
    setNewImage(null)
  }

  const openEdit = () => {
    if (!query.data) return
    setEditData({
      title: query.data.title || "",
      content: query.data.content || "",
      title_en: query.data.title_en || "",
      content_en: query.data.content_en || "",
      image_url: query.data.image_url || "",
    })
    resetPreview()
    setEditOpen(true)
  }

  const closeEdit = () => {
    resetPreview()
    setEditOpen(false)
  }

  const handleImageChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setNewImage(file)
    setPreviewUrl(URL.createObjectURL(file))
  }

  const handleSave = async () => {
    if (!query.data) return
    setSaving(true)
    try {
      let imageUrl = editData.image_url
      if (newImage) {
        const uploaded = await uploadNewsImage(newImage)
        imageUrl = uploaded
      }
      const payload = {
        title: editData.title,
        content: editData.content,
        title_en: editData.title_en,
        content_en: editData.content_en,
        image_url: imageUrl,
      }
      const { data } = await updateNews(query.data.id, payload)
      queryClient.setQueryData(["news", id, language], data)
      await queryClient.invalidateQueries({ queryKey: ["news", "list"] })
      setSnackbar(t("news:notifications.savedError"))
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!query.data) return
    setDeleting(true)
    try {
      await deleteNews(query.data.id)
      setSnackbar(t("news:notifications.deleted"))
      queryClient.removeQueries({ queryKey: ["news", id] })
      await queryClient.invalidateQueries({ queryKey: ["news", "list"] })
      if (window.history.length > 1) navigate(-1)
      else navigate("/news")
    } catch (_error) {
      setSnackbar(t("news:notifications.deleteError"))
    } finally {
      setDeleting(false)
      setConfirmDeleteOpen(false)
    }
  }

  const handleBack = () => {
    if (window.history.length > 1) navigate(-1)
    else navigate("/news")
  }

  const rawImageUrl = useMemo(
    () => (editOpen ? editData.image_url : query.data?.image_url) || "",
    [editData.image_url, editOpen, query.data?.image_url]
  )

  const imageUrl = useMemo(() => {
    if (previewUrl) return previewUrl
    return rawImageUrl
  }, [previewUrl, rawImageUrl])

  useEffect(() => {
    setHeroRatio(null)
  }, [imageUrl])

  const displayTitle = useMemo(() => {
    const localized = query.data?.title ?? ""
    const english = query.data?.title_en ?? ""
    if (language === "en" && english.trim()) return english
    return localized || english
  }, [language, query.data?.title, query.data?.title_en])

  const content = useMemo(() => {
    const localized = query.data?.content ?? ""
    const english = query.data?.content_en ?? ""
    if (language === "en" && english.trim()) return english
    return localized || english
  }, [language, query.data?.content, query.data?.content_en])
  const createdAt = query.data?.created_at
  const createdAtIso = useMemo(() => (createdAt ? dayjs(createdAt).toISOString() : ""), [createdAt])
  const createdAtLabel = useMemo(() => (createdAt ? getMoscowDate(createdAt) : ""), [createdAt])

  const readingTimeMinutes = useMemo(() => {
    const text = content
      .replace(/<[^>]+>/g, " ")
      .replace(/\s+/g, " ")
      .trim()
    if (!text) return null

    const words = text.split(/\s+/).filter(Boolean).length
    if (!words) return null

    const wordsPerMinute = 220
    return Math.max(1, Math.round(words / wordsPerMinute))
  }, [content])

  if (query.isLoading) {
    return (
      <Layout>
        <div className="flex min-h-(--h-hero-lg) items-center justify-center">
          <span className="h-12 w-12 animate-spin rounded-full border-2 border-white/(--opacity-soft) border-t-(--brand-main)" />
        </div>
      </Layout>
    )
  }

  if (query.isError || !query.data)
    return (
      <Layout>
        <div className="px-4 py-10">
          <p className="text-lg font-semibold text-(--error-text)">{t("news:states.loadError")}</p>
        </div>
      </Layout>
    )

  return (
    <Layout>
      <div className="flex w-full flex-col gap-(--fluid-gap) px-(--fluid-px) pb-16 pt-6 sm:gap-8 sm:pt-8 lg:px-(--fluid-px)">
        <Button
          variant="outline"
          onClick={handleBack}
          leadingIcon={<ArrowBackIcon className="text-lg" />}
          className="w-fit justify-start border-white/(--opacity-dim) text-base"
        >
          {t("common:buttons.back")}
        </Button>

        <article className="flex w-full flex-col items-start gap-8">
          <header className="flex w-full flex-col gap-4 text-left">
            <h1 className="max-w-5xl text-fluid-h1 font-extrabold tracking-tight text-text-primary">
              {displayTitle}
            </h1>

            <SEO title={displayTitle} description={content.slice(0, 160)} image={imageUrl} />

            <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
              <div className="flex flex-wrap items-center gap-2 text-sm text-(--text-secondary)">
                {createdAt ? (
                  <span className="inline-flex items-center gap-2 rounded-full border border-(--glass-border) bg-(--bg-surface)/(--opacity-subtle) px-3 py-1 text-xs font-semibold uppercase tracking-widest text-(--text-secondary)">
                    <span>{t("news:meta.published")}</span>
                    <span aria-hidden>•</span>
                    <time dateTime={createdAtIso} className="text-text-primary">
                      {createdAtLabel}
                    </time>
                  </span>
                ) : null}

                {readingTimeMinutes !== null && (
                  <span className="inline-flex items-center gap-2 rounded-pill border border-(--glass-border)/(--opacity-dim) bg-(--bg-surface)/(--opacity-subtle) px-3 py-1 text-xs font-medium tracking-wide text-text-primary">
                    {t("news:meta.readingTime", { count: readingTimeMinutes ?? undefined })}
                  </span>
                )}

                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    void handleShare()
                  }}
                  leadingIcon={<IosShareIcon size={16} />}
                  className="w-full basis-full sm:w-auto sm:basis-auto"
                  loading={sharing}
                  aria-label={t("news:aria.shareNews") ?? ""}
                >
                  {t("news:actions.share")}
                </Button>

                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => toggleLike()}
                  leadingIcon={
                    <FavoriteIcon
                      className={cn(
                        "h-4 w-4",
                        isLiked
                          ? "fill-(--error-text) text-(--error-text)"
                          : "text-(--text-secondary)"
                      )}
                    />
                  }
                  className={cn(
                    "w-full basis-full sm:w-auto sm:basis-auto transition-colors duration-fast",
                    isLiked
                      ? "border-(--error-text)/(--opacity-dim) bg-(--error-text)/(--opacity-subtle)"
                      : "border-(--glass-border)/(--opacity-soft) bg-(--bg-surface)/(--opacity-medium)"
                  )}
                >
                  <span className="tabular-nums">{likesCount}</span>
                </Button>
              </div>
            </div>

            {user?.role === "admin" ? (
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={openEdit}
                  className={iconButtonClass}
                  aria-label={t("news:aria.editNews") ?? ""}
                  disabled={saving || deleting}
                >
                  <EditIcon size={16} />
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmDeleteOpen(true)}
                  className={cn(
                    iconButtonClass,
                    "text-(--error-text) hover:text-(--error-text)/(--opacity-hover)"
                  )}
                  aria-label={t("news:aria.deleteNews") ?? ""}
                  disabled={deleting || saving}
                >
                  <DeleteIcon className="h-5 w-5" />
                </button>
              </div>
            ) : null}
          </header>

          <figure className="w-full max-w-5xl self-start overflow-hidden rounded-lg border border-(--glass-border) bg-(--bg-surface)/(--opacity-medium) shadow-glass backdrop-blur-md">
            <div
              className={cn(
                "flex w-full items-center justify-center overflow-hidden",
                heroFrame.container,
                heroFrame.backdrop
              )}
            >
              <SmartImage
                srcRaw={imageUrl}
                alt={
                  displayTitle
                    ? t("news:alt.hero", { title: displayTitle })
                    : t("news:alt.heroFallback")
                }
                onLoad={handleHeroLoad}
                className={cn("h-full w-full", heroFrame.image)}
              />
            </div>
            {displayTitle ? null : (
              <figcaption className="border-t border-(--glass-border) bg-(--bg-surface)/(--opacity-subtle) px-5 py-3 text-sm font-medium text-(--text-secondary)">
                {t("news:alt.heroFallback")}
              </figcaption>
            )}
          </figure>

          <section className="max-w-4xl self-start space-y-(--fluid-gap) text-body leading-relaxed text-(--text-secondary)">
            {content?.split(/\n{2,}/).map((chunk: string, index: number) => {
              const text = chunk.trim()

              if (!text) return null

              return <p key={`news-detail-paragraph-${index}`}>{text}</p>
            })}
          </section>

          <NewsComments
            comments={comments}
            user={user}
            isCommenting={isCommenting}
            addComment={addComment}
            updateComment={updateComment}
            deleteComment={deleteComment}
            t={t}
            getMoscowDate={getMoscowDate}
          />
        </article>
      </div>

      <Dialog
        open={shareDialogOpen}
        onClose={() => setShareDialogOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>{t("news:shareDialog.title")}</DialogTitle>
        <DialogContent className="space-y-6 pt-4">
          <p className="text-base leading-relaxed text-(--text-secondary)">
            {t("news:shareDialog.description")}
          </p>

          <div className="grid gap-3 sm:grid-cols-3">
            {shareOptions.map((option) => {
              const Icon = option.icon
              return (
                <a
                  key={`share-option-${option.id}`}
                  href={option.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={() => setShareDialogOpen(false)}
                  className="group flex items-center gap-3 rounded-md border border-(--glass-border)/(--opacity-dim) bg-(--bg-surface)/(--opacity-medium) px-4 py-3 transition hover:border-(--glass-border)/(--opacity-soft) hover:bg-(--bg-surface)/(--opacity-strong)"
                >
                  <span
                    className={cn(
                      "inline-flex h-10 w-10 items-center justify-center rounded-full bg-(--bg-surface)/(--opacity-hover) shadow-sm transition group-hover:scale-105",
                      option.accent
                    )}
                  >
                    <Icon className="h-5 w-5" />
                  </span>
                  <span className="text-sm font-semibold text-text-primary">{option.label}</span>
                </a>
              )
            })}
          </div>
        </DialogContent>
        <DialogActions className="p-6">
          <Button
            variant="solid"
            onClick={() => {
              void handleCopyLink()
            }}
            disabled={copyingLink}
            className="w-full sm:w-auto"
          >
            <div className="flex items-center gap-2">
              <ContentCopyIcon className="h-4 w-4" />
              {copiedLink ? t("news:shareDialog.copySuccess") : t("news:shareDialog.copy")}
            </div>
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={editOpen} onClose={closeEdit} maxWidth="lg" fullWidth>
        <DialogTitle>{t("news:dialogs.edit.title")}</DialogTitle>
        <DialogContent className="space-y-6 pt-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-4">
              <Field label={t("news:form.title") ?? ""} htmlFor="edit-title" required>
                <Input
                  id="edit-title"
                  ref={editTitleRef}
                  type="text"
                  value={editData.title}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                    setEditData({ ...editData, title: e.target.value })
                  }
                  maxLength={100}
                />
              </Field>

              <Field label={t("news:form.content") ?? ""} htmlFor="edit-content" required>
                <Textarea
                  id="edit-content"
                  value={editData.content}
                  onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) =>
                    setEditData({ ...editData, content: e.target.value })
                  }
                  maxLength={3000}
                  rows={6}
                />
              </Field>
            </div>

            <div className="space-y-4">
              <Field
                label={t("news:form.title_en", { defaultValue: "Title (English)" }) ?? ""}
                htmlFor="edit-title-en"
              >
                <Input
                  id="edit-title-en"
                  type="text"
                  value={editData.title_en}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                    setEditData({ ...editData, title_en: e.target.value })
                  }
                  maxLength={100}
                />
              </Field>

              <Field
                label={t("news:form.content_en", { defaultValue: "News text (English)" }) ?? ""}
                htmlFor="edit-content-en"
              >
                <Textarea
                  id="edit-content-en"
                  value={editData.content_en}
                  onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) =>
                    setEditData({ ...editData, content_en: e.target.value })
                  }
                  maxLength={3000}
                  rows={6}
                />
              </Field>

              <div className="space-y-3">
                <label className="block text-sm font-semibold text-(--text-secondary)">
                  {t("news:form.image", { defaultValue: "Cover Image" })}
                </label>
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                  <Button
                    as="label"
                    variant="outline"
                    className="w-full sm:w-auto bg-(--bg-surface)/(--opacity-dim) border-glass-border"
                    disabled={saving}
                  >
                    <div className="flex items-center gap-2">
                      <PhotoCamera className="h-4 w-4" />
                      {newImage ? t("common:buttons.changePhoto") : t("common:buttons.uploadPhoto")}
                    </div>
                    <input
                      type="file"
                      accept="image/*"
                      hidden
                      ref={imageInputRef}
                      onChange={handleImageChange}
                    />
                  </Button>

                  {imageUrl ? (
                    <div className="overflow-hidden rounded-sm border border-glass-border shadow-sm">
                      <SmartImage
                        srcRaw={imageUrl}
                        alt={t("news:alt.editPreview")}
                        className="h-14 w-28 object-cover"
                      />
                    </div>
                  ) : null}
                </div>
                {previewUrl && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={resetPreview}
                    className="text-(--error-text)"
                  >
                    {t("common:buttons.reset")}
                  </Button>
                )}
              </div>
            </div>
          </div>
        </DialogContent>
        <DialogActions className="flex-col-reverse gap-3 sm:flex-row p-6">
          <Button variant="ghost" onClick={closeEdit} className="w-full sm:w-auto">
            {t("common:buttons.cancel")}
          </Button>
          <Button
            variant="solid"
            onClick={handleSave}
            disabled={!editData.title.trim() || !editData.content.trim() || saving}
            className="w-full sm:w-auto min-w-32"
          >
            {saving ? t("common:buttons.saving") : t("common:buttons.save")}
          </Button>
        </DialogActions>
      </Dialog>

      <ConfirmDialog
        open={confirmDeleteOpen}
        title={t("news:dialogs.delete.title")}
        message={t("news:dialogs.delete.description")}
        confirmText={t("common:buttons.delete")}
        cancelText={t("common:buttons.cancel")}
        variant="danger"
        onConfirm={() => void handleDelete()}
        onCancel={() => setConfirmDeleteOpen(false)}
        isLoading={deleting}
      />

      {snackbar && (
        <Snackbar
          open={!!snackbar}
          autoHideDuration={2400}
          onClose={() => setSnackbar("")}
          anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
          className="z-navbar"
        >
          <Alert severity="success" onClose={() => setSnackbar("")}>
            {snackbar}
          </Alert>
        </Snackbar>
      )}
    </Layout>
  )
}
