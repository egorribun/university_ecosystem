import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type CSSProperties,
} from "react"
import { useNavigate, useParams } from "react-router-dom"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import ArrowBackIcon from "@mui/icons-material/ArrowBack"
import EditIcon from "@mui/icons-material/Edit"
import DeleteIcon from "@mui/icons-material/Delete"
import SaveIcon from "@mui/icons-material/Save"
import CloseIcon from "@mui/icons-material/Close"
import PhotoCamera from "@mui/icons-material/PhotoCamera"
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
  const readingMinutes = useMemo(() => {
    if (!content) return null
    const words = content.split(/\s+/).filter((word) => word.trim().length > 0)
    if (!words.length) return null
    return Math.max(1, Math.round(words.length / 180))
  }, [content])
  const contentParagraphs = useMemo(() => {
    if (!content) return []
    return content
      .split(/\n{2,}/)
      .map((chunk) => chunk.trim())
      .filter((chunk) => chunk.length > 0)
  }, [content])

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
      <div className="relative isolate">
        <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
          <div className="absolute -left-[14%] top-[-12%] h-[520px] w-[520px] rounded-full bg-[radial-gradient(circle_at_center,rgba(59,130,246,0.24),transparent_68%)] blur-3xl opacity-75" />
          <div className="absolute right-[-16%] top-[18%] h-[460px] w-[460px] rounded-full bg-[radial-gradient(circle_at_center,rgba(124,58,237,0.28),transparent_70%)] blur-3xl opacity-70" />
          <div className="absolute bottom-[-22%] left-[10%] h-[380px] w-[380px] rounded-full bg-[radial-gradient(circle_at_center,rgba(14,165,233,0.2),transparent_70%)] blur-3xl opacity-60" />
        </div>

        <div className="flex w-full flex-col gap-8 px-4 pb-16 pt-5 sm:px-6 lg:px-8">
          <Button
            data-fade
            variant="outline"
            onClick={handleBack}
            leadingIcon={<ArrowBackIcon className="text-[1.1rem]" />}
            className="w-fit justify-start border-white/20 text-[clamp(0.95rem,2vw,1.1rem)] [--fade-delay:80ms]"
          >
            {t("common:buttons.back")}
          </Button>

          <article className="relative flex w-full flex-col items-start gap-8">
            <header data-fade className="flex w-full flex-col gap-4 text-left [--fade-delay:140ms]">
              <div className="max-w-5xl space-y-3">
                <h1 className="text-balance text-[clamp(1.7rem,4.6vw,2.6rem)] font-extrabold tracking-tight text-[color:var(--page-text)]">
                  {displayTitle}
                </h1>
                <p className="text-[0.95rem] font-medium uppercase tracking-[0.32em] text-[color:color-mix(in_srgb,var(--secondary-text)_80%,white_20%)]">
                  {t("news:pageTagline", {
                    defaultValue: "In-depth insights shaping our academic community",
                  })}
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {createdAt ? (
                  <span className="inline-flex items-center gap-2 rounded-ue-pill border border-white/14 bg-[color:var(--glass-bg)]/70 px-3 py-1.5 text-[0.72rem] font-semibold uppercase tracking-[0.26em] text-[color:color-mix(in_srgb,var(--secondary-text)_85%,white_15%)]">
                    {t("news:meta.published")}
                    <time dateTime={createdAtIso} className="text-[color:var(--page-text)]">
                      {createdAtLabel}
                    </time>
                  </span>
                ) : null}

                {readingMinutes ? (
                  <span className="inline-flex items-center gap-2 rounded-ue-pill border border-white/14 bg-[color:var(--glass-bg)]/65 px-3 py-1.5 text-[0.72rem] font-semibold uppercase tracking-[0.26em] text-[color:color-mix(in_srgb,var(--secondary-text)_85%,white_15%)]">
                    {t("news:meta.readingTime", {
                      count: readingMinutes,
                      defaultValue: `${readingMinutes} min read`,
                    })}
                  </span>
                ) : null}
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

            <figure
              data-fade
              className="group/hero relative w-full max-w-5xl self-start overflow-hidden rounded-ue-xl border border-white/12 bg-[color:var(--glass-bg)]/60 shadow-surface [--fade-delay:200ms]"
            >
              <span
                aria-hidden
                className="pointer-events-none absolute inset-0 z-[1] bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.28),transparent_75%)] opacity-0 transition duration-700 ease-out group-hover/hero:opacity-100"
              />
              <div
                className={cn(
                  "relative flex w-full items-center justify-center overflow-hidden",
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
                  className={cn(
                    "h-full w-full transition duration-700 ease-out motion-safe:group-hover/hero:scale-[1.03]",
                    heroFrame.image
                  )}
                />
              </div>
              {displayTitle ? null : (
                <figcaption className="relative border-t border-white/10 bg-[color:var(--glass-bg)]/70 px-5 py-3 text-sm font-medium text-[color:var(--secondary-text)]">
                  {t("news:alt.heroFallback")}
                </figcaption>
              )}
            </figure>

            <section className="max-w-4xl self-start space-y-5 text-[1.05rem]">
              {contentParagraphs.map((text, index) => (
                <p
                  key={`news-detail-paragraph-${index}`}
                  data-fade
                  style={{ "--fade-delay": `${260 + index * 50}ms` } as CSSProperties}
                  className="group/paragraph relative overflow-hidden rounded-ue-xl border border-transparent bg-transparent px-5 py-4 text-[color:var(--secondary-text)] leading-[1.85] transition duration-300 ease-out hover:border-white/12 hover:bg-[color:color-mix(in_srgb,var(--card-bg)_86%,white_14%)] sm:px-6"
                >
                  <span className="relative z-[1] block">{text}</span>
                  <span
                    aria-hidden
                    className="pointer-events-none absolute inset-0 rounded-ue-xl bg-[radial-gradient(circle_at_top,rgba(148,163,255,0.18),transparent_65%)] opacity-0 transition duration-500 ease-out group-hover/paragraph:opacity-100"
                  />
                </p>
              ))}
            </section>
          </article>
        </div>
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
        <div className="fixed bottom-6 left-1/2 z-[999] w-[min(90vw,360px)] -translate-x-1/2 overflow-hidden rounded-ue-lg border border-white/12 bg-[color:color-mix(in_srgb,var(--card-bg)_94%,white_6%)]/95 px-4 py-3 text-center text-[0.95rem] font-semibold text-[color:var(--page-text)] shadow-surface-strong backdrop-blur-xl">
          <span aria-hidden className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(148,163,255,0.16),transparent_65%)]" />
          <span aria-hidden className="pointer-events-none absolute inset-x-6 top-0 h-px bg-gradient-to-r from-transparent via-white/45 to-transparent" />
          <span className="relative block">{snack}</span>
        </div>
      ) : null}
    </Layout>
  )
}
