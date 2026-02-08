import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import {
  ArrowLeft as ArrowBackIcon,
  Edit2 as EditIcon,
  Trash2 as DeleteIcon,
  Save as SaveIcon,
  X as CloseIcon,
  Camera as PhotoCamera,
  Share2 as IosShareIcon,
  Copy as ContentCopyIcon,
  Send as SendIcon,
  Heart as FavoriteIcon,
  MessageSquare as ChatBubbleOutlineIcon,
  MessageCircle as WhatsAppIcon,
  Mail as AlternateEmailIcon,
  Send as TelegramIcon,
} from "lucide-react"
import {
  Alert,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
} from "@/components/settings"
import { useNewsInteraction } from "@/hooks/useNewsInteraction"
import dayjs from "dayjs"
import utc from "dayjs/plugin/utc"
import timezone from "dayjs/plugin/timezone"
import { deleteNews, fetchNewsItem, updateNews, uploadNewsImage, type NewsItem } from "@/api/news"
import Layout from "@/components/Layout"
import SmartImage from "@/components/SmartImage"
import { Button } from "@/components/ui"
import { useAuth } from "@/contexts/AuthContext"
import { useLanguage } from "@/contexts/LanguageContext"
// import { invalidateNewsFeed } from "@/hooks/useNewsFeed"
import { useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"

dayjs.extend(utc)
dayjs.extend(timezone)

const inputClass =
    "w-full rounded-xl border border-glass-border bg-surface/40 px-4 py-2.5 text-[0.98rem] text-primary-text shadow-sm focus:border-brand focus:outline-none transition placeholder:text-secondary-text/50"
const textareaClass = cn(inputClass, "min-h-[160px] resize-y leading-relaxed")
const iconButtonClass =
    "inline-flex h-10 w-10 items-center justify-center rounded-full border border-glass-border bg-surface/80 text-secondary-text shadow-sm transition hover:bg-surface hover:text-primary-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"

type FieldProps = {
  label: ReactNode
  htmlFor: string
  children: ReactNode
  required?: boolean
}

function Field({ label, htmlFor, children, required = false }: FieldProps) {
  return (
    <div className="space-y-2">
      <label
        htmlFor={htmlFor}
        className="text-sm font-semibold tracking-wide text-secondary-text/80"
      >
        {label}
        {required ? <span className="ml-1 text-red-500">*</span> : null}
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
  if (!/([Zz]|[+\-]\d\d:?\d\d)$/.test(dateStr)) parsed = dayjs.utc(dateStr)
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
  const [snack, setSnack] = useState("")
  const [sharing, setSharing] = useState(false)
  const [shareDialogOpen, setShareDialogOpen] = useState(false)
  const [copyingLink, setCopyingLink] = useState(false)
  const [copiedLink, setCopiedLink] = useState(false)
  const imageInputRef = useRef<HTMLInputElement>(null)
  const editTitleRef = useRef<HTMLInputElement>(null)
  const [heroRatio, setHeroRatio] = useState<number | null>(null)
  const copyTimeoutRef = useRef<number | null>(null)
  const [commentText, setCommentText] = useState("")

  const { data: newsItem } = useQuery<NewsItem>({ queryKey: ["news", id, language] })

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

  const [editingCommentId, setEditingCommentId] = useState<number | null>(null)
  const [editingCommentText, setEditingCommentText] = useState("")

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
        container: "min-h-[320px] h-[clamp(320px,56vh,520px)] max-h-[520px]",
        image: "object-cover object-[50%_40%]",
        backdrop: "bg-black/20",
      }
    }

    const ratio = Math.min(Math.max(heroRatio, 0.35), 4)

    if (ratio < 0.82) {
      return {
        container: "min-h-[440px] max-h-[82vh] aspect-[3/4]",
        image: "object-contain object-center",
        backdrop: "bg-black/25",
      }
    }

    if (ratio < 1.18) {
      return {
        container: "min-h-[360px] max-h-[76vh] aspect-[5/4]",
        image: "object-cover object-[50%_38%]",
        backdrop: "bg-surface/20",
      }
    }

    if (ratio > 2.6) {
      return {
        container: "min-h-[260px] max-h-[60vh] aspect-[21/9]",
        image: "object-cover object-[50%_46%]",
        backdrop: "bg-black/20",
      }
    }

    return {
      container: "min-h-[300px] max-h-[68vh] aspect-video",
      image: "object-cover object-[50%_40%]",
      backdrop: "bg-surface/20",
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
    if (!snack) return
    const timeout = window.setTimeout(() => setSnack(""), 2400)
    return () => window.clearTimeout(timeout)
  }, [snack])

  useEffect(() => {
    if (shareDialogOpen) return
    if (copyTimeoutRef.current) {
      window.clearTimeout(copyTimeoutRef.current)
      copyTimeoutRef.current = null
    }
    setCopiedLink(false)
  }, [shareDialogOpen])

  useEffect(() => {
    return () => {
      if (copyTimeoutRef.current) {
        window.clearTimeout(copyTimeoutRef.current)
        copyTimeoutRef.current = null
      }
    }
  }, [])

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

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
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
      setSnack(t("news:notifications.updated"))
      closeEdit()
    } catch (error) {
      console.error(error)
      setSnack(t("news:notifications.savedError"))
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!query.data) return
    setDeleting(true)
    try {
      await deleteNews(query.data.id)
      setSnack(t("news:notifications.deleted"))
      queryClient.removeQueries({ queryKey: ["news", id] })
      await queryClient.invalidateQueries({ queryKey: ["news", "list"] })
      if (window.history.length > 1) navigate(-1)
      else navigate("/news")
    } catch (error) {
      console.error(error)
      setSnack(t("news:notifications.deleteError"))
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

  const shareUrl = useMemo(() => {
    if (typeof window === "undefined") return ""
    return window.location.href
  }, [id, language])

  const shareOptions = useMemo(() => {
    if (!shareUrl) return []
    const encodedUrl = encodeURIComponent(shareUrl)
    const shareTitle = displayTitle || t("news:pageTitle")
    const encodedTitle = encodeURIComponent(shareTitle)

    return [
      {
        id: "telegram",
        label: t("news:shareDialog.options.telegram", { defaultValue: "Telegram" }),
        href: `https://t.me/share/url?url=${encodedUrl}&text=${encodedTitle}`,
        icon: <TelegramIcon className="h-4 w-4" />,
        accent: "text-brand",
      },
      {
        id: "whatsapp",
        label: t("news:shareDialog.options.whatsapp", { defaultValue: "WhatsApp" }),
        href: `https://api.whatsapp.com/send?text=${encodedTitle}%20${encodedUrl}`,
        icon: <WhatsAppIcon className="h-4 w-4" />,
        accent: "text-green-500",
      },
      {
        id: "email",
        label: t("news:shareDialog.options.email", { defaultValue: "Email" }),
        href: `mailto:?subject=${encodedTitle}&body=${encodedTitle}%0A${encodedUrl}`,
        icon: <AlternateEmailIcon className="h-4 w-4" />,
        accent: "text-brand/80",
      },
    ]
  }, [displayTitle, shareUrl, t])

  const handleShare = useCallback(async () => {
    if (sharing) return

    const url = typeof window !== "undefined" ? window.location.href : ""
    if (!url) return

    const title = displayTitle || t("news:pageTitle")
    const shareData = {
      title,
      text: title,
      url,
    }

    const canUseNativeShare =
      typeof navigator !== "undefined" &&
      typeof navigator.share === "function" &&
      (!navigator.canShare || navigator.canShare(shareData))

    try {
      setSharing(true)
      if (canUseNativeShare) {
        await navigator.share(shareData)
        setSnack(t("news:notifications.shareSuccess"))
      } else {
        setShareDialogOpen(true)
      }
    } catch (error) {
      const message = (error as DOMException | Error)?.name ?? ""
      if (message === "AbortError") return
      console.error(error)
      setSnack(t("news:notifications.shareError"))
    } finally {
      setSharing(false)
    }
  }, [displayTitle, sharing, t])

  const handleCopyLink = useCallback(async () => {
    if (!shareUrl || copyingLink) return
    setCopyingLink(true)

    try {
      if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(shareUrl)
      } else {
        const textarea = document.createElement("textarea")
        textarea.value = shareUrl
        textarea.setAttribute("readonly", "")
        textarea.style.position = "absolute"
        textarea.style.left = "-9999px"
        document.body.appendChild(textarea)
        textarea.select()
        document.execCommand("copy")
        document.body.removeChild(textarea)
      }

      setCopiedLink(true)
      const msg = t("news:notifications.linkCopied")

      setSnack(msg)
      if (copyTimeoutRef.current) {
        window.clearTimeout(copyTimeoutRef.current)
      }
      copyTimeoutRef.current = window.setTimeout(() => {
        setCopiedLink(false)
        copyTimeoutRef.current = null
      }, 2200)
    } catch (error) {
      console.error(error)
      setSnack(t("news:notifications.shareError"))
    } finally {
      setCopyingLink(false)
    }
  }, [copyingLink, shareUrl, t])

    return (
      <Layout>
        <div className="flex min-h-[60vh] items-center justify-center">
          <span className="h-12 w-12 animate-spin rounded-full border-2 border-white/30 border-t-brand" />
        </div>
      </Layout>
    )

  if (query.isError || !query.data)
    return (
      <Layout>
        <div className="px-4 py-10">
          <p className="text-lg font-semibold text-[#f87171]">{t("news:states.loadError")}</p>
        </div>
      </Layout>
    )

  return (
    <Layout>
      <div className="flex w-full flex-col gap-6 px-4 pb-16 pt-4 sm:gap-8 sm:px-6 sm:pt-6 lg:px-8">
        <Button
          variant="outline"
          onClick={handleBack}
          leadingIcon={<ArrowBackIcon className="text-[1.1rem]" />}
          className="w-fit justify-start border-white/20 text-[clamp(0.95rem,2vw,1.1rem)]"
        >
          {t("common:buttons.back")}
        </Button>

        <article className="flex w-full flex-col items-start gap-8">
          <header className="flex w-full flex-col gap-4 text-left">
            <h1 className="max-w-5xl text-[clamp(1.6rem,4vw,2.4rem)] font-extrabold tracking-tight text-(--page-text)">
              {displayTitle}
            </h1>

            <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
              <div className="flex flex-wrap items-center gap-2 text-[0.9rem] text-secondary-text">
                {createdAt ? (
                  <span className="inline-flex items-center gap-2 rounded-full border border-glass-border bg-surface/10 px-3 py-1 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-secondary-text">
                    <span>{t("news:meta.published")}</span>
                    <span aria-hidden>•</span>
                    <time dateTime={createdAtIso} className="text-primary-text">
                      {createdAtLabel}
                    </time>
                  </span>
                ) : null}

                {readingTimeMinutes !== null && (
                  <span className="inline-flex items-center gap-2 rounded-full border border-glass-border/20 bg-surface/10 px-3 py-1 text-[0.78rem] font-medium tracking-wide text-primary-text">
                    {t("news:meta.readingTime", { count: readingTimeMinutes ?? undefined })}
                  </span>
                )}

                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    void handleShare()
                  }}
                  leadingIcon={<IosShareIcon fontSize="small" />}
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
                      className={cn("h-4 w-4", isLiked ? "fill-rose-500 text-rose-500" : "text-secondary-text")}
                    />
                  }
                  className={cn(
                    "w-full basis-full sm:w-auto sm:basis-auto transition-colors duration-200",
                    isLiked ? "border-rose-200/30 bg-rose-500/10" : "border-glass-border/30 bg-surface/40"
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
                  <EditIcon fontSize="small" />
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmDeleteOpen(true)}
                  className={cn(iconButtonClass, "text-red-500 hover:text-red-400")}
                  aria-label={t("news:aria.deleteNews") ?? ""}
                  disabled={deleting || saving}
                >
                  <DeleteIcon className="h-5 w-5" />
                </button>
              </div>
            ) : null}
          </header>

          <figure className="w-full max-w-5xl self-start overflow-hidden rounded-3xl border border-glass-border bg-surface/40 shadow-glass backdrop-blur-md">
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
              <figcaption className="border-t border-glass-border bg-surface/10 px-5 py-3 text-sm font-medium text-secondary-text">
                {t("news:alt.heroFallback")}
              </figcaption>
            )}
          </figure>

          <section className="max-w-4xl self-start space-y-6 text-[1.05rem] leading-8 text-secondary-text">
            {content?.split(/\n{2,}/).map((chunk: string, index: number) => {
              const text = chunk.trim()

              if (!text) return null

              return <p key={`news-detail-paragraph-${index}`}>{text}</p>
            })}
          </section>

          <footer className="w-full max-w-4xl mt-12 border-t border-glass-border/30 pt-10">
            <div className="flex items-center gap-3 mb-8">
              <ChatBubbleOutlineIcon className="h-6 w-6 text-brand" />
              <h2 className="text-xl font-bold text-primary-text">
                {t("news:sections.comments", { defaultValue: "Комментарии" })}
              </h2>
              <span className="px-2 py-0.5 rounded-full bg-brand/10 border border-brand/20 text-xs font-bold tabular-nums text-brand">
                {comments.length}
              </span>
            </div>

            <div className="space-y-6 mb-10">
              {comments.length === 0 ? (
                <p className="text-secondary-text italic py-4">
                  {t("news:states.noComments", {
                    defaultValue: "Пока нет ни одного комментария. Будьте первым!",
                  })}
                </p>
              ) : (
                comments.map((comment) => (
                  <div
                    key={comment.id}
                    className="flex flex-col gap-2 p-4 rounded-2xl bg-surface/20 border border-glass-border/30 shadow-sm"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-sm text-primary-text">
                        {comment.user_name}
                      </span>
                      <div className="flex items-center gap-3">
                        <time className="text-[0.7rem] text-secondary-text uppercase font-semibold">
                          {getMoscowDate(comment.created_at)}
                        </time>
                        {(user?.id === comment.user_id || user?.role === "admin") && (
                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => {
                                setEditingCommentId(comment.id)
                                setEditingCommentText(comment.content)
                              }}
                              className="p-1.5 rounded-full hover:bg-surface/60 text-secondary-text hover:text-primary-text transition-colors"
                              title={t("news:actions.editComment", { defaultValue: "Edit" }) ?? ""}
                            >
                              <EditIcon className="h-3.5 w-3.5" />
                            </button>
                            <button
                              onClick={() => {
                                if (
                                  confirm(
                                    t("news:dialogs.deleteComment.confirm", {
                                      defaultValue: "Delete this comment?",
                                    }) ?? "Delete this comment?"
                                  )
                                ) {
                                  void deleteComment(comment.id)
                                }
                              }}
                              className="p-1.5 rounded-full hover:bg-rose-500/10 text-rose-500 hover:text-rose-400 transition-colors"
                              title={
                                t("news:actions.deleteComment", { defaultValue: "Delete" }) ?? ""
                              }
                            >
                              <DeleteIcon className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                    {editingCommentId === comment.id ? (
                      <div className="space-y-3 mt-1">
                        <textarea
                          value={editingCommentText}
                          onChange={(e) => setEditingCommentText(e.target.value)}
                          className={cn(textareaClass, "min-h-[80px] text-sm")}
                          autoFocus
                        />
                        <div className="flex justify-end gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setEditingCommentId(null)}
                          >
                            {t("common:buttons.cancel")}
                          </Button>
                          <Button
                            size="sm"
                            onClick={() => {
                              if (editingCommentText.trim()) {
                                void updateComment(comment.id, editingCommentText)
                                setEditingCommentId(null)
                              }
                            }}
                            disabled={!editingCommentText.trim()}
                          >
                            {t("common:buttons.save")}
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <p className="text-[0.95rem] leading-relaxed whitespace-pre-wrap">
                        {comment.content}
                      </p>
                    )}
                  </div>
                ))
              )}
            </div>

            {user && (
              <div className="space-y-4">
                <textarea
                  value={commentText}
                  onChange={(e) => setCommentText(e.target.value)}
                  placeholder={t("news:form.commentPlaceholder", {
                    defaultValue: "Напишите что-нибудь...",
                  })}
                  className={cn(textareaClass, "min-h-[100px]")}
                />
                <div className="flex justify-end">
                  <Button
                    onClick={() => {
                      if (commentText.trim()) {
                        addComment(commentText)
                        setCommentText("")
                      }
                    }}
                    disabled={!commentText.trim() || isCommenting}
                    loading={isCommenting}
                    leadingIcon={<SendIcon fontSize="small" />}
                  >
                    {t("news:actions.postComment", { defaultValue: "Отправить" })}
                  </Button>
                </div>
              </div>
            )}
          </footer>
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
          <p className="text-[0.95rem] leading-relaxed text-secondary-text">
            {t("news:shareDialog.description")}
          </p>

          <div className="grid gap-3 sm:grid-cols-3">
            {shareOptions.map((option) => (
              <a
                key={`share-option-${option.id}`}
                href={option.href}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => setShareDialogOpen(false)}
                className="group flex items-center gap-3 rounded-2xl border border-glass-border/20 bg-surface/40 px-4 py-3 transition hover:border-glass-border/40 hover:bg-surface/60"
              >
                <span
                  className={cn(
                    "inline-flex h-10 w-10 items-center justify-center rounded-full bg-surface/80 text-[1.2rem] shadow-sm transition group-hover:scale-105",
                    option.id === "telegram" ? "text-brand" : option.id === "whatsapp" ? "text-green-500" : "text-brand/80"
                  )}
                >
                  {option.id === "telegram" ? <TelegramIcon className="h-5 w-5" /> : option.id === "whatsapp" ? <WhatsAppIcon className="h-5 w-5" /> : <AlternateEmailIcon className="h-5 w-5" />}
                </span>
                <span className="text-sm font-semibold text-primary-text">
                  {option.label}
                </span>
              </a>
            ))}
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

      <Dialog
        open={editOpen}
        onClose={closeEdit}
        maxWidth="lg"
        fullWidth
      >
        <DialogTitle>{t("news:dialogs.edit.title")}</DialogTitle>
        <DialogContent className="space-y-6 pt-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-4">
              <Field label={t("news:form.title") ?? ""} htmlFor="edit-title" required>
                <input
                  id="edit-title"
                  ref={editTitleRef}
                  type="text"
                  value={editData.title}
                  onChange={(e) => setEditData({ ...editData, title: e.target.value })}
                  maxLength={100}
                  className={inputClass}
                />
              </Field>

              <Field label={t("news:form.content") ?? ""} htmlFor="edit-content" required>
                <textarea
                  id="edit-content"
                  value={editData.content}
                  onChange={(e) => setEditData({ ...editData, content: e.target.value })}
                  maxLength={3000}
                  className={textareaClass}
                  rows={6}
                />
              </Field>
            </div>

            <div className="space-y-4">
              <Field
                label={t("news:form.title_en", { defaultValue: "Title (English)" }) ?? ""}
                htmlFor="edit-title-en"
              >
                <input
                  id="edit-title-en"
                  type="text"
                  value={editData.title_en}
                  onChange={(e) => setEditData({ ...editData, title_en: e.target.value })}
                  maxLength={100}
                  className={inputClass}
                />
              </Field>

              <Field
                label={t("news:form.content_en", { defaultValue: "News text (English)" }) ?? ""}
                htmlFor="edit-content-en"
              >
                <textarea
                  id="edit-content-en"
                  value={editData.content_en}
                  onChange={(e) => setEditData({ ...editData, content_en: e.target.value })}
                  maxLength={3000}
                  className={textareaClass}
                  rows={6}
                />
              </Field>

              <div className="space-y-3">
                <label className="block text-sm font-semibold text-secondary-text">
                  {t("news:form.image", { defaultValue: "Cover Image" })}
                </label>
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                  <Button
                    as="label"
                    variant="outline"
                    className="w-full sm:w-auto bg-surface/20 border-glass-border"
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
                    <div className="overflow-hidden rounded-xl border border-glass-border shadow-sm">
                      <SmartImage
                        srcRaw={imageUrl}
                        alt={t("news:alt.editPreview")}
                        className="h-14 w-28 object-cover"
                      />
                    </div>
                  ) : null}
                </div>
                {previewUrl && (
                   <Button variant="ghost" size="sm" onClick={resetPreview} className="text-rose-500">
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
            className="w-full sm:w-auto min-w-[120px]"
          >
            {saving ? t("common:buttons.saving") : t("common:buttons.save")}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={confirmDeleteOpen}
        onClose={() => setConfirmDeleteOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>{t("news:dialogs.delete.title")}</DialogTitle>
        <DialogContent className="space-y-4">
          <p className="text-[0.98rem] text-secondary-text">
            {t("news:dialogs.delete.description")}
          </p>
        </DialogContent>
        <DialogActions className="flex-col-reverse gap-3 sm:flex-row p-6">
          <Button
            variant="ghost"
            onClick={() => setConfirmDeleteOpen(false)}
            disabled={deleting}
            className="w-full sm:w-auto"
          >
            {t("common:buttons.cancel")}
          </Button>
          <Button
            variant="solid"
            onClick={() => {
              void handleDelete()
            }}
            disabled={deleting}
            className="w-full bg-linear-to-r from-red-600 to-red-700 text-white hover:from-red-700 hover:to-red-800 sm:w-auto"
          >
            <div className="flex items-center gap-2">
               <DeleteIcon className="h-4 w-4" />
               {deleting ? t("common:statuses.deleting") : t("common:buttons.delete")}
            </div>
          </Button>
        </DialogActions>
      </Dialog>

      {snack && (
         <div className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 animate-in fade-in slide-in-from-bottom-4">
           <Alert
             severity="success"
             onClose={() => setSnack("")}
             className="min-w-[300px] shadow-glass border-glass-border bg-surface/90"
           >
             {snack}
           </Alert>
         </div>
      )}
    </Layout>
  )
}
