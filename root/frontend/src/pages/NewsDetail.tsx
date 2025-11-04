import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import ArrowBackIcon from "@mui/icons-material/ArrowBack"
import EditIcon from "@mui/icons-material/Edit"
import DeleteIcon from "@mui/icons-material/Delete"
import SaveIcon from "@mui/icons-material/Save"
import CloseIcon from "@mui/icons-material/Close"
import PhotoCamera from "@mui/icons-material/PhotoCamera"
import IosShareIcon from "@mui/icons-material/IosShare"
import ContentCopyIcon from "@mui/icons-material/ContentCopy"
import TelegramIcon from "@mui/icons-material/Telegram"
import WhatsAppIcon from "@mui/icons-material/WhatsApp"
import AlternateEmailIcon from "@mui/icons-material/AlternateEmail"
import dayjs from "dayjs"
import utc from "dayjs/plugin/utc"
import timezone from "dayjs/plugin/timezone"
import { deleteNews, fetchNewsItem, updateNews, uploadNewsImage } from "@/api/news"
import Layout from "@/components/Layout"
import SmartImage from "@/components/SmartImage"
import { Button } from "@/components/ui"
import Dialog from "@/components/Dialog"
import { useAuth } from "@/contexts/AuthContext"
import { useLanguage } from "@/contexts/LanguageContext"
import { useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"

dayjs.extend(utc)
dayjs.extend(timezone)

const inputClass =
  "w-full rounded-ue-lg border border-white/12 bg-[color:color-mix(in_srgb,var(--card-bg)_94%,white_6%)] px-4 py-2.5 text-[0.98rem] text-[color:var(--page-text)] shadow-[inset_0_1px_0_rgba(15,23,42,0.08)] transition focus:border-[color:var(--nav-link)] focus:outline-none focus:shadow-focus placeholder:text-[color:var(--placeholder-fg)]"
const textareaClass = `${inputClass} min-h-[160px] resize-y leading-relaxed`
const iconButtonClass =
  "inline-flex h-10 w-10 items-center justify-center rounded-full border border-white/15 bg-white/85 text-[color:var(--nav-link)] shadow-surface transition hover:bg-white focus-visible:outline-none focus-visible:shadow-focus"

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
        className="text-sm font-semibold tracking-wide text-[color:color-mix(in_srgb,var(--secondary-text)_85%,white_15%)]"
      >
        {label}
        {required ? <span className="ml-1 text-[#f87171]">*</span> : null}
      </label>
      {children}
    </div>
  )
}

async function fetchNews(id: string) {
  const numericId = Number(id)
  if (!Number.isFinite(numericId)) {
    throw new Error("Invalid news id")
  }
  const response = await fetchNewsItem(numericId)
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
        backdrop: "bg-[color:color-mix(in_srgb,var(--glass-bg)_80%,black_20%)]",
      }
    }

    const ratio = Math.min(Math.max(heroRatio, 0.35), 4)

    if (ratio < 0.82) {
      return {
        container: "min-h-[440px] max-h-[82vh] aspect-[3/4]",
        image: "object-contain object-center",
        backdrop: "bg-[color:color-mix(in_srgb,var(--glass-bg)_75%,black_25%)]",
      }
    }

    if (ratio < 1.18) {
      return {
        container: "min-h-[360px] max-h-[76vh] aspect-[5/4]",
        image: "object-cover object-[50%_38%]",
        backdrop: "bg-[var(--glass-bg)]",
      }
    }

    if (ratio > 2.6) {
      return {
        container: "min-h-[260px] max-h-[60vh] aspect-[21/9]",
        image: "object-cover object-[50%_46%]",
        backdrop: "bg-[color:color-mix(in_srgb,var(--glass-bg)_80%,black_20%)]",
      }
    }

    return {
      container: "min-h-[300px] max-h-[68vh] aspect-video",
      image: "object-cover object-[50%_40%]",
      backdrop: "bg-[var(--glass-bg)]",
    }
  }, [heroRatio])

  const query = useQuery({
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
      await queryClient.invalidateQueries({ queryKey: ["news"] })
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
      await queryClient.invalidateQueries({ queryKey: ["news"] })
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
        icon: <TelegramIcon fontSize="small" />,
        accent: "text-[#229ED9]",
      },
      {
        id: "whatsapp",
        label: t("news:shareDialog.options.whatsapp", { defaultValue: "WhatsApp" }),
        href: `https://api.whatsapp.com/send?text=${encodedTitle}%20${encodedUrl}`,
        icon: <WhatsAppIcon fontSize="small" />,
        accent: "text-[#25D366]",
      },
      {
        id: "email",
        label: t("news:shareDialog.options.email", { defaultValue: "Email" }),
        href: `mailto:?subject=${encodedTitle}&body=${encodedTitle}%0A${encodedUrl}`,
        icon: <AlternateEmailIcon fontSize="small" />,
        accent: "text-[#6366F1]",
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
      setSnack(t("news:notifications.linkCopied"))
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

  if (query.isLoading)
    return (
      <Layout>
        <div className="flex min-h-[60vh] items-center justify-center">
          <span className="h-12 w-12 animate-spin rounded-full border-2 border-white/30 border-t-[color:var(--nav-link)]" />
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
      <div className="flex w-full max-w-[1200px] mx-auto flex-col gap-8 px-4 pb-16 pt-5 sm:px-6 lg:px-8">
        <Button
          variant="outline"
          onClick={handleBack}
          leadingIcon={<ArrowBackIcon className="text-[0.95rem]" />}
          size="sm"
          className="w-fit justify-start border-white/20 text-[0.9rem] px-3 py-1.5 h-9 hover:bg-white/10 transition-all duration-200"
        >
          {t("common:buttons.back")}
        </Button>

        <article className="flex w-full flex-col items-start gap-8">
          <header className="flex w-full flex-col gap-4 text-left">
            <h1 className="w-full max-w-4xl text-[clamp(1.6rem,4vw,2.4rem)] font-extrabold tracking-tight text-[color:var(--page-text)] leading-tight">
              {displayTitle}
            </h1>

            <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
              <div className="flex flex-wrap items-center gap-2.5 text-[0.9rem] text-[color:var(--secondary-text)]">
                {createdAt ? (
                  <span className="inline-flex items-center gap-2 rounded-full border border-white/12 bg-white/5 px-3 py-1.5 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-[color:var(--secondary-text)] backdrop-blur-sm">
                    <span>{t("news:meta.published")}</span>
                    <span aria-hidden>•</span>
                    <time dateTime={createdAtIso} className="text-[color:var(--page-text)]">
                      {createdAtLabel}
                    </time>
                  </span>
                ) : null}

                {readingTimeMinutes !== null ? (
                  <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-[0.78rem] font-medium tracking-wide text-[color:var(--page-text)] backdrop-blur-sm">
                    {t("news:meta.readingTime", { count: readingTimeMinutes })}
                  </span>
                ) : null}

                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    void handleShare()
                  }}
                  leadingIcon={<IosShareIcon fontSize="small" />}
                  className="w-full basis-full sm:w-auto sm:basis-auto border-white/20 hover:bg-white/10"
                  loading={sharing}
                  aria-label={t("news:aria.shareNews") ?? ""}
                >
                  {t("news:actions.share")}
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
                  className={cn(iconButtonClass, "text-[#e11d48]")}
                  aria-label={t("news:aria.deleteNews") ?? ""}
                  disabled={deleting || saving}
                >
                  <DeleteIcon fontSize="small" />
                </button>
              </div>
            ) : null}
          </header>

          <figure className="w-full max-w-4xl self-start overflow-hidden rounded-ue-xl border border-white/12 bg-[color:var(--glass-bg)]/60 shadow-surface-strong backdrop-blur-sm">
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
              <figcaption className="border-t border-white/10 bg-[color:var(--glass-bg)]/70 px-5 py-3 text-sm font-medium text-[color:var(--secondary-text)] backdrop-blur-sm">
                {t("news:alt.heroFallback")}
              </figcaption>
            )}
          </figure>

          <section className="w-full max-w-4xl self-start space-y-6 text-[1.05rem] leading-8 text-[color:var(--secondary-text)]">
            {content?.split(/\n{2,}/).map((chunk, index) => {
              const text = chunk.trim()

              if (!text) return null

              return <p key={`news-detail-paragraph-${index}`}>{text}</p>
            })}
          </section>
        </article>
      </div>

      <Dialog
        open={shareDialogOpen}
        onClose={() => setShareDialogOpen(false)}
        title={t("news:shareDialog.title")}
        subtitle={t("news:shareDialog.subtitle")}
        bodyClassName="space-y-4"
        footer={
          <Button
            onClick={() => {
              void handleCopyLink()
            }}
            loading={copyingLink}
            leadingIcon={<ContentCopyIcon fontSize="small" />}
            className="w-full sm:w-auto"
          >
            {copiedLink ? t("news:shareDialog.copySuccess") : t("news:shareDialog.copy")}
          </Button>
        }
        footerClassName="sm:flex-row sm:justify-end"
      >
        <p className="text-[0.95rem] leading-relaxed text-[color:var(--secondary-text)]">
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
              className="group flex items-center gap-3 rounded-ue-lg border border-white/10 bg-white/5 px-4 py-3 transition hover:border-white/20 hover:bg-white/10"
            >
              <span
                className={cn(
                  "inline-flex h-10 w-10 items-center justify-center rounded-full bg-white/80 text-[1.2rem] text-[color:var(--nav-link)] shadow-surface transition group-hover:scale-105",
                  option.accent
                )}
              >
                {option.icon}
              </span>
              <span className="text-sm font-semibold text-[color:var(--page-text)]">
                {option.label}
              </span>
            </a>
          ))}
        </div>
      </Dialog>

      <Dialog
        open={editOpen}
        onClose={closeEdit}
        title={t("news:dialogs.edit.title")}
        size="md"
        fullScreenOnMobile
        closeLabel={t("common:buttons.close")}
        bodyClassName="space-y-4"
        footerClassName="flex-col-reverse gap-3 sm:flex-row"
        footer={
          <>
            <Button
              variant="outline"
              onClick={closeEdit}
              disabled={saving}
              className="w-full sm:w-auto"
              leadingIcon={<CloseIcon fontSize="small" />}
            >
              {t("common:buttons.cancel")}
            </Button>
            <Button
              onClick={() => {
                void handleSave()
              }}
              disabled={saving}
              loading={saving}
              className="w-full sm:w-auto"
              leadingIcon={<SaveIcon fontSize="small" />}
            >
              {t("common:buttons.save")}
            </Button>
          </>
        }
        initialFocus={() => editTitleRef.current ?? undefined}
      >
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            void handleSave()
          }}
        >
          <Field label={t("news:form.title") ?? ""} htmlFor="news-detail-title" required>
            <input
              id="news-detail-title"
              ref={editTitleRef}
              type="text"
              value={editData.title}
              onChange={(e) => setEditData({ ...editData, title: e.target.value })}
              disabled={saving}
              className={inputClass}
            />
          </Field>

          <Field label={t("news:form.text") ?? ""} htmlFor="news-detail-content" required>
            <textarea
              id="news-detail-content"
              value={editData.content}
              onChange={(e) => setEditData({ ...editData, content: e.target.value })}
              disabled={saving}
              className={textareaClass}
              rows={5}
            />
          </Field>

          <Field
            label={t("news:form.title_en", { defaultValue: "Title (English)" }) ?? ""}
            htmlFor="news-detail-title-en"
          >
            <input
              id="news-detail-title-en"
              type="text"
              value={editData.title_en}
              onChange={(e) => setEditData({ ...editData, title_en: e.target.value })}
              disabled={saving}
              className={inputClass}
            />
          </Field>

          <Field
            label={t("news:form.content_en", { defaultValue: "News text (English)" }) ?? ""}
            htmlFor="news-detail-content-en"
          >
            <textarea
              id="news-detail-content-en"
              value={editData.content_en}
              onChange={(e) => setEditData({ ...editData, content_en: e.target.value })}
              disabled={saving}
              className={textareaClass}
              rows={5}
            />
          </Field>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <Button
              as="label"
              variant="outline"
              size="sm"
              leadingIcon={<PhotoCamera className="text-[1.15rem]" />}
              className="w-full sm:w-auto"
              disabled={saving}
            >
              {newImage ? t("news:form.changePhoto") : t("news:form.uploadPhoto")}
              <input
                type="file"
                accept="image/*"
                hidden
                ref={imageInputRef}
                onChange={handleImageChange}
              />
            </Button>

            {imageUrl ? (
              <SmartImage
                srcRaw={imageUrl}
                alt={t("news:alt.preview")}
                className="h-20 w-full max-w-[180px] rounded-ue-md border border-white/10 object-cover shadow-surface"
              />
            ) : null}
          </div>
        </form>
      </Dialog>

      <Dialog
        open={confirmDeleteOpen}
        onClose={() => setConfirmDeleteOpen(false)}
        title={t("news:dialogs.delete.title")}
        bodyClassName="space-y-4"
        footer={
          <>
            <Button
              variant="outline"
              onClick={() => setConfirmDeleteOpen(false)}
              disabled={deleting}
              className="w-full sm:w-auto"
            >
              {t("common:buttons.cancel")}
            </Button>
            <Button
              onClick={() => {
                void handleDelete()
              }}
              disabled={deleting}
              loading={deleting}
              className="w-full bg-[linear-gradient(98deg,#dc2626,#b91c1c)] text-white hover:bg-[linear-gradient(98deg,#b91c1c,#991b1b)] sm:w-auto"
              leadingIcon={<DeleteIcon fontSize="small" />}
            >
              {t("common:buttons.delete")}
            </Button>
          </>
        }
      >
        <p className="text-[0.98rem] text-[color:var(--secondary-text)]">
          {t("news:dialogs.delete.description")}
        </p>
      </Dialog>

      {snack ? (
        <div className="fixed bottom-6 left-1/2 z-[999] w-[min(90vw,360px)] -translate-x-1/2 rounded-ue-lg border border-white/12 bg-[color:color-mix(in_srgb,var(--card-bg)_94%,white_6%)]/95 px-4 py-3 text-center text-[0.95rem] font-semibold text-[color:var(--page-text)] shadow-surface-strong backdrop-blur-xl">
          {snack}
        </div>
      ) : null}
    </Layout>
  )
}
