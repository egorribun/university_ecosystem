import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type SVGProps,
} from "react"
import { useNavigate, useParams } from "react-router-dom"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import ArrowBackIcon from "@mui/icons-material/ArrowBack"
import EditIcon from "@mui/icons-material/Edit"
import DeleteIcon from "@mui/icons-material/Delete"
import SaveIcon from "@mui/icons-material/Save"
import CloseIcon from "@mui/icons-material/Close"
import PhotoCamera from "@mui/icons-material/PhotoCamera"
import TelegramIcon from "@mui/icons-material/Telegram"
import WhatsAppIcon from "@mui/icons-material/WhatsApp"
import dayjs from "dayjs"
import utc from "dayjs/plugin/utc"
import timezone from "dayjs/plugin/timezone"
import { deleteNews, fetchNewsItem, updateNews, uploadNewsImage } from "@/api/news"
import Layout from "@/components/Layout"
import SmartImage from "@/components/SmartImage"
import { Button } from "@/components/ui"
import { Tooltip } from "@/components/ui/tooltip"
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

function VkIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" {...props}>
      <path d="m9.489.004.729-.003h3.564l.73.003.914.01.433.007.418.011.403.014.388.016.374.021.36.025.345.03.333.033c1.74.196 2.933.616 3.833 1.516.9.9 1.32 2.092 1.516 3.833l.034.333.029.346.025.36.02.373.025.588.012.41.013.644.009.915.004.98-.001 3.313-.003.73-.01.914-.007.433-.011.418-.014.403-.016.388-.021.374-.025.36-.03.345-.033.333c-.196 1.74-.616 2.933-1.516 3.833-.9.9-2.092 1.32-3.833 1.516l-.333.034-.346.029-.36.025-.373.02-.588.025-.41.012-.644.013-.915.009-.98.004-3.313-.001-.73-.003-.914-.01-.433-.007-.418-.011-.403-.014-.388-.016-.374-.021-.36-.025-.345-.03-.333-.033c-1.74-.196-2.933-.616-3.833-1.516-.9-.9-1.32-2.092-1.516-3.833l-.034-.333-.029-.346-.025-.36-.02-.373-.025-.588-.012-.41-.013-.644-.009-.915-.004-.98.001-3.313.003-.73.01-.914.007-.433.011-.418.014-.403.016-.388.021-.374.025-.36.03-.345.033-.333c.196-1.74.616-2.933 1.516-3.833.9-.9 2.092-1.32 3.833-1.516l.333-.034.346-.029.36-.025.373-.02.588-.025.41-.012.644-.013.915-.009ZM6.79 7.3H4.05c.13 6.24 3.25 9.99 8.72 9.99h.31v-3.57c2.01.2 3.53 1.67 4.14 3.57h2.84c-.78-2.84-2.83-4.41-4.11-5.01 1.28-.74 3.08-2.54 3.51-4.98h-2.58c-.56 1.98-2.22 3.78-3.8 3.95V7.3H10.5v6.92c-1.6-.4-3.62-2.34-3.71-6.92Z" />
    </svg>
  )
}

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
  const [shareUrl, setShareUrl] = useState("")
  const imageInputRef = useRef<HTMLInputElement>(null)
  const editTitleRef = useRef<HTMLInputElement>(null)
  const [heroRatio, setHeroRatio] = useState<number | null>(null)

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
    if (typeof window === "undefined") return
    setShareUrl(window.location.href)
  }, [id])

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
  const readingMinutes = useMemo(() => {
    const text = content || ""
    if (!text.trim()) return 1
    const words = text
      .split(/\s+/)
      .map((word) => word.trim())
      .filter(Boolean).length
    if (!words) return 1
    return Math.max(1, Math.round(words / 180))
  }, [content])
  const createdAt = query.data?.created_at
  const createdAtIso = useMemo(() => (createdAt ? dayjs(createdAt).toISOString() : ""), [createdAt])
  const createdAtLabel = useMemo(() => (createdAt ? getMoscowDate(createdAt) : ""), [createdAt])
  const shareFallbackTitle = t("news:meta.shareDefaultTitle")
  const shareTargets = useMemo(() => {
    const currentUrl = shareUrl || (typeof window !== "undefined" ? window.location.href : "")
    const message = (displayTitle && displayTitle.trim()) || shareFallbackTitle
    const encodedUrl = encodeURIComponent(currentUrl)
    const encodedMessage = encodeURIComponent(message)
    const messageWithUrl = encodedMessage + (encodedUrl ? `%20${encodedUrl}` : "")

    return [
      {
        id: "vk",
        name: "VK",
        href: `https://vk.com/share.php?url=${encodedUrl}&title=${encodedMessage}`,
        renderIcon: (className: string) => <VkIcon className={className} />,
      },
      {
        id: "telegram",
        name: "Telegram",
        href: `https://t.me/share/url?url=${encodedUrl}&text=${encodedMessage}`,
        renderIcon: (className: string) => <TelegramIcon className={className} fontSize="inherit" />,
      },
      {
        id: "whatsapp",
        name: "WhatsApp",
        href: `https://api.whatsapp.com/send?text=${messageWithUrl}`,
        renderIcon: (className: string) => <WhatsAppIcon className={className} fontSize="inherit" />,
      },
    ]
  }, [displayTitle, shareFallbackTitle, shareUrl])
  const shareTooltipLabel = t("news:meta.shareTooltip")

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
      <div className="flex w-full flex-col gap-8 px-4 pb-16 pt-5 sm:px-6 lg:px-8">
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
            <h1 className="max-w-5xl text-[clamp(1.6rem,4vw,2.4rem)] font-extrabold tracking-tight text-[color:var(--page-text)]">
              {displayTitle}
            </h1>

            {createdAt ? (
              <p className="text-sm font-medium uppercase tracking-[0.18em] text-[color:var(--secondary-text)]">
                {t("news:meta.published")}
                <span className="ml-2 font-semibold text-[color:var(--page-text)]">
                  <time dateTime={createdAtIso}>{createdAtLabel}</time>
                </span>
              </p>
            ) : null}

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

          <section className="w-full max-w-5xl self-start rounded-ue-xl border border-white/12 bg-[color:var(--glass-bg)]/70 p-5 shadow-surface">
            <div className="grid gap-6 sm:grid-cols-2">
              <div className="space-y-4">
                <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.18em] text-[color:var(--secondary-text)]">
                  <span aria-hidden className="text-base text-[color:var(--nav-link)]">◆</span>
                  {t("news:meta.shareHeading")}
                </div>
                <div className="flex flex-wrap gap-3">
                  {shareTargets.map(({ id, name, href, renderIcon }) => (
                    <Tooltip key={id} content={shareTooltipLabel}>
                      <a
                        href={href}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-white/15 bg-white/10 text-white/80 shadow-[0_10px_30px_rgba(15,23,42,0.18)] transition hover:bg-white/20 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--nav-link)] focus-visible:ring-offset-2 focus-visible:ring-offset-transparent"
                        aria-label={t("news:aria.shareOn", { network: name }) ?? undefined}
                      >
                        {renderIcon("h-5 w-5")}
                      </a>
                    </Tooltip>
                  ))}
                </div>
              </div>

              <div className="space-y-3 rounded-ue-lg border border-white/10 bg-[color:color-mix(in_srgb,var(--glass-bg)_85%,black_15%)]/70 p-4">
                <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.18em] text-[color:var(--secondary-text)]">
                  <span aria-hidden className="text-base text-[color:var(--nav-link)]">◆</span>
                  {t("news:meta.readingHeading")}
                </div>
                <p className="text-[clamp(1.05rem,2vw,1.2rem)] font-semibold text-[color:var(--page-text)]">
                  {t("news:meta.readingTimeLabel", { count: readingMinutes })}
                </p>
                <p className="text-sm leading-6 text-[color:var(--secondary-text)]">{t("news:meta.readingTimeNote")}</p>
              </div>
            </div>
          </section>

          <figure className="w-full max-w-5xl self-start overflow-hidden rounded-ue-xl border border-white/12 bg-[color:var(--glass-bg)]/60 shadow-surface">
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
              <figcaption className="border-t border-white/10 bg-[color:var(--glass-bg)]/70 px-5 py-3 text-sm font-medium text-[color:var(--secondary-text)]">
                {t("news:alt.heroFallback")}
              </figcaption>
            )}
          </figure>

          <section className="max-w-4xl self-start space-y-6 text-[1.05rem] leading-8 text-[color:var(--secondary-text)]">
            {content?.split(/\n{2,}/).map((chunk, index) => {
              const text = chunk.trim()

              if (!text) return null

              return <p key={`news-detail-paragraph-${index}`}>{text}</p>
            })}
          </section>
        </article>
      </div>

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
