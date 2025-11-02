import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react"
import { useNavigate, useParams } from "react-router-dom"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import ArrowBackIcon from "@mui/icons-material/ArrowBack"
import EditIcon from "@mui/icons-material/Edit"
import DeleteIcon from "@mui/icons-material/Delete"
import SaveIcon from "@mui/icons-material/Save"
import CloseIcon from "@mui/icons-material/Close"
import PhotoCamera from "@mui/icons-material/PhotoCamera"
import ShareIcon from "@mui/icons-material/Share"
import LinkIcon from "@mui/icons-material/Link"
import { IconButton, Tooltip } from "@mui/material"
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

type ToastStatus = "success" | "error" | "info"

type ToastState = {
  id: number
  message: string
  status: ToastStatus
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
  const [toast, setToast] = useState<ToastState | null>(null)
  const imageInputRef = useRef<HTMLInputElement>(null)
  const editTitleRef = useRef<HTMLInputElement>(null)
  const [heroRatio, setHeroRatio] = useState<number | null>(null)
  const progressRef = useRef<HTMLDivElement>(null)
  const toastTimerRef = useRef<number | null>(null)

  const TOAST_DURATION = 3600

  const showToast = useCallback((message: string, status: ToastStatus = "info") => {
    setToast({ id: Date.now(), message, status })
  }, [])

  const updateProgress = useCallback(() => {
    const doc = document.documentElement
    const scrollable = doc.scrollHeight - window.innerHeight
    const progress = scrollable > 0 ? Math.min(Math.max(window.scrollY / scrollable, 0), 1) : 1
    if (progressRef.current) {
      progressRef.current.style.setProperty("--progress", progress.toString())
      progressRef.current.style.opacity = progress > 0.005 ? "1" : "0"
    }
  }, [])

  const handleHeroLoad = useCallback<React.ReactEventHandler<HTMLImageElement>>(
    (event) => {
      const img = event.currentTarget
      const width = img.naturalWidth || 0
      const height = img.naturalHeight || 0
      if (!width || !height) return

      setHeroRatio(width / height)
      window.requestAnimationFrame(() => {
        updateProgress()
      })
    },
    [updateProgress]
  )

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
    updateProgress()
    window.addEventListener("scroll", updateProgress, { passive: true })
    window.addEventListener("resize", updateProgress)
    return () => {
      window.removeEventListener("scroll", updateProgress)
      window.removeEventListener("resize", updateProgress)
    }
  }, [updateProgress])

  useEffect(() => {
    return () => {
      if (toastTimerRef.current) {
        window.clearTimeout(toastTimerRef.current)
        toastTimerRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    if (!toast) return
    if (toastTimerRef.current) {
      window.clearTimeout(toastTimerRef.current)
    }
    const timer = window.setTimeout(() => {
      setToast(null)
      toastTimerRef.current = null
    }, TOAST_DURATION)
    toastTimerRef.current = timer
    return () => {
      window.clearTimeout(timer)
    }
  }, [TOAST_DURATION, toast])

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
      showToast(t("news:notifications.updated"), "success")
      closeEdit()
    } catch (error) {
      console.error(error)
      showToast(t("news:notifications.savedError"), "error")
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!query.data) return
    setDeleting(true)
    try {
      await deleteNews(query.data.id)
      showToast(t("news:notifications.deleted"), "success")
      queryClient.removeQueries({ queryKey: ["news", id] })
      await queryClient.invalidateQueries({ queryKey: ["news"] })
      if (window.history.length > 1) navigate(-1)
      else navigate("/news")
    } catch (error) {
      console.error(error)
      showToast(t("news:notifications.deleteError"), "error")
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

  const contentNodes = useMemo<ReactNode[]>(() => {
    if (!content) return []

    return content
      .split(/\n{2,}/)
      .map((chunk, index) => {
        const text = chunk.trim()
        if (!text) return null

        const lines = text
          .split(/\n/)
          .map((line) => line.trim())
          .filter(Boolean)
        if (!lines.length) return null

        if (lines.every((line) => /^[-*]\s+/.test(line))) {
          return (
            <ul key={`news-detail-list-${index}`}>
              {lines.map((line, itemIndex) => (
                <li key={`news-detail-list-${index}-${itemIndex}`}>
                  {line.replace(/^[-*]\s+/, "").trim()}
                </li>
              ))}
            </ul>
          )
        }

        if (lines.every((line) => /^\d+[.)]\s+/.test(line))) {
          return (
            <ol key={`news-detail-ordered-${index}`}>
              {lines.map((line, itemIndex) => (
                <li key={`news-detail-ordered-${index}-${itemIndex}`}>
                  {line.replace(/^\d+[.)]\s+/, "").trim()}
                </li>
              ))}
            </ol>
          )
        }

        if (text.startsWith(">")) {
          const quote = lines
            .map((line) => line.replace(/^>\s?/, ""))
            .join("\n")
            .trim()
          return (
            <blockquote key={`news-detail-quote-${index}`}>
              {quote.split(/\n{2,}/).map((paragraph, quoteIndex) => (
                <p key={`news-detail-quote-${index}-${quoteIndex}`}>{paragraph.trim()}</p>
              ))}
            </blockquote>
          )
        }

        const segments = text.split(/\n/)

        return (
          <p key={`news-detail-paragraph-${index}`}>
            {segments.map((segment, segmentIndex) => (
              <span key={`news-detail-paragraph-${index}-${segmentIndex}`}>
                {segment.trim()}
                {segmentIndex < segments.length - 1 ? <br /> : null}
              </span>
            ))}
          </p>
        )
      })
      .filter(Boolean) as ReactNode[]
  }, [content])

  const actionsDescriptionId = useMemo(() => `news-actions-${id ?? "item"}`, [id])

  const handleCopyLink = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(window.location.href)
      showToast(
        t("news:notifications.linkCopied", { defaultValue: "Link copied to clipboard" }),
        "success"
      )
    } catch (error) {
      console.error(error)
      showToast(
        t("news:notifications.linkCopyError", { defaultValue: "Unable to copy link" }),
        "error"
      )
    }
  }, [showToast, t])

  const handleShare = useCallback(async () => {
    const shareTitle =
      displayTitle || t("news:share.fallbackTitle", { defaultValue: "University news" })
    const shareData = {
      title: shareTitle,
      text: shareTitle,
      url: window.location.href,
    }

    if (navigator.share) {
      try {
        await navigator.share(shareData)
        showToast(
          t("news:notifications.shareOpened", { defaultValue: "Share dialog opened" }),
          "success"
        )
      } catch (error) {
        if ((error as DOMException)?.name === "AbortError") return
        console.error(error)
        showToast(t("news:notifications.shareError", { defaultValue: "Unable to share" }), "error")
      }
      return
    }

    await handleCopyLink()
  }, [displayTitle, handleCopyLink, showToast, t])

  const heroBackdropStyle = useMemo<CSSProperties | undefined>(
    () => (imageUrl ? ({ "--hero-src": `url(${imageUrl})` } as CSSProperties) : undefined),
    [imageUrl]
  )

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
      <div
        ref={progressRef}
        className="pointer-events-none fixed left-0 top-0 z-[1200] h-[3px] w-full overflow-hidden bg-transparent opacity-0 transition-opacity duration-300 ease-out"
        aria-hidden="true"
      >
        <span className="block h-full w-full origin-left scale-x-[var(--progress,0)] bg-[linear-gradient(96deg,var(--nav-link),color-mix(in_srgb,var(--nav-link)_42%,#06b6d4_58%))] shadow-[0_0_14px_rgba(14,165,233,0.52)] transition-[transform] duration-200 ease-out will-change-transform" />
      </div>

      <div className="flex w-full flex-col gap-8 px-4 pb-24 pt-5 sm:px-6 lg:px-8">
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

          <div className="relative flex w-full flex-col gap-6 lg:flex-row lg:items-start lg:gap-10">
            <div
              className={cn(
                "relative isolate w-full max-w-5xl self-start before:pointer-events-none before:absolute before:-inset-x-[min(16vw,140px)] before:-top-[24vh] before:-bottom-[26vh] before:-z-10 before:bg-[image:var(--hero-src)] before:bg-cover before:bg-center before:bg-no-repeat before:opacity-0 before:blur-[120px] before:transition-opacity before:duration-[900ms] before:ease-out before:content-[''] motion-reduce:before:transition-none",
                imageUrl ? "data-[has-image=true]:before:opacity-40" : "before:opacity-0"
              )}
              data-has-image={Boolean(imageUrl)}
              style={heroBackdropStyle}
            >
              <figure className="relative w-full overflow-hidden rounded-ue-xl border border-white/12 bg-[color:var(--glass-bg)]/60 shadow-surface backdrop-blur">
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
            </div>

            <aside
              role="region"
              aria-label={t("news:aria.shareActions", { defaultValue: "Article actions" }) ?? ""}
              aria-describedby={actionsDescriptionId}
              className="pointer-events-auto fixed bottom-6 left-1/2 z-[1090] w-[min(92vw,360px)] -translate-x-1/2 rounded-ue-xl border border-white/15 bg-[color:color-mix(in_srgb,var(--card-bg)_78%,transparent_22%)]/85 p-4 text-[color:var(--page-text)] shadow-surface backdrop-blur-2xl transition-all duration-500 ease-out motion-reduce:transition-none md:static md:ml-auto md:w-auto md:translate-x-0 md:rounded-ue-lg md:border-white/12 md:bg-[color:color-mix(in_srgb,var(--glass-bg)_70%,black_30%)]/85 md:p-5 md:shadow-glass lg:sticky lg:top-28"
            >
              <p
                id={actionsDescriptionId}
                className="text-[0.72rem] font-semibold uppercase tracking-[0.28em] text-[color:var(--secondary-text)]"
              >
                {t("news:actions.title", { defaultValue: "Share this story" })}
              </p>
              <p className="mt-2 text-sm text-[color:color-mix(in_srgb,var(--secondary-text)_88%,white_12%)]">
                {t("news:actions.helper", { defaultValue: "Spread the word or save the link" })}
              </p>
              <div className="mt-4 flex items-center justify-between gap-3">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  leadingIcon={<ShareIcon fontSize="small" />}
                  className="flex-1 border-white/25 text-[0.95rem] font-semibold shadow-surface"
                  onClick={() => {
                    void handleShare()
                  }}
                >
                  {t("news:actions.share", { defaultValue: "Share" })}
                </Button>
                <Tooltip
                  title={t("news:actions.copyLink", { defaultValue: "Copy link" })}
                  placement="top"
                  arrow
                >
                  <IconButton
                    onClick={() => {
                      void handleCopyLink()
                    }}
                    aria-describedby={actionsDescriptionId}
                    aria-label={t("news:actions.copyLink", { defaultValue: "Copy link" }) ?? ""}
                    className="!h-11 !w-11 rounded-full border border-white/25 bg-white/10 text-[color:var(--page-text)] shadow-surface transition duration-200 ease-out hover:bg-white/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-0 focus-visible:ring-[color:var(--nav-link)]"
                    size="large"
                  >
                    <LinkIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </div>
            </aside>
          </div>

          <section className="prose-neutral">{contentNodes.length ? contentNodes : null}</section>
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

      {toast ? (
        <div className="pointer-events-none fixed inset-x-0 bottom-0 z-[1200] flex justify-center px-4 pb-5 pt-4">
          <div
            key={toast.id}
            className={cn(
              "toast-bubble",
              toast.status === "success"
                ? "toast-bubble--success"
                : toast.status === "error"
                  ? "toast-bubble--error"
                  : "toast-bubble--info"
            )}
            data-status={toast.status}
            role={toast.status === "error" ? "alert" : "status"}
            aria-live={toast.status === "error" ? "assertive" : "polite"}
            style={{ "--toast-duration": `${TOAST_DURATION}ms` } as CSSProperties}
          >
            {toast.message}
            <span className="toast-bubble__progress" aria-hidden="true" />
          </div>
        </div>
      ) : null}
    </Layout>
  )
}
