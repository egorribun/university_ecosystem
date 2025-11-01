import { useEffect, useMemo, useRef, useState, useId } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import ArrowBackIcon from "@mui/icons-material/ArrowBack"
import EditIcon from "@mui/icons-material/Edit"
import DeleteIcon from "@mui/icons-material/Delete"
import PhotoCamera from "@mui/icons-material/PhotoCamera"
import dayjs from "dayjs"
import utc from "dayjs/plugin/utc"
import timezone from "dayjs/plugin/timezone"
import { deleteNews, fetchNewsItem, updateNews, uploadNewsImage } from "@/api/news"
import Layout from "@/components/Layout"
import SmartImage from "@/components/SmartImage"
import { useAuth } from "@/contexts/AuthContext"
import { useLanguage } from "@/contexts/LanguageContext"
import { useTranslation } from "react-i18next"
import useMediaQuery from "@/hooks/useMediaQuery"
import { Button, Modal, ModalBody, ModalFooter, ModalHeader, modalFieldStyles } from "@/components/ui"
import { cn } from "@/utils/cn"

dayjs.extend(utc)
dayjs.extend(timezone)

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
  const isMobile = useMediaQuery("(max-width: 640px)")

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
  const [heroPos, setHeroPos] = useState<"50% 18%" | "50% 38%" | "50% 50%" | string>("50% 38%")

  const editDialogTitleId = useId()
  const deleteDialogTitleId = useId()
  const editTitleId = useId()
  const editContentId = useId()
  const editTitleEnId = useId()
  const editContentEnId = useId()
  const editFileInputId = useId()

  const handleHeroLoad: React.ReactEventHandler<HTMLImageElement> = (e) => {
    const img = e.currentTarget
    const w = img.naturalWidth || 0
    const h = img.naturalHeight || 0
    if (!w || !h) return
    const r = w / h
    if (r < 0.9) setHeroPos("50% 18%")
    else if (r > 2) setHeroPos("50% 50%")
    else setHeroPos("50% 38%")
  }

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
    const timer = window.setTimeout(() => setSnack(""), 2600)
    return () => window.clearTimeout(timer)
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
    [editData.image_url, editOpen, query.data?.image_url],
  )

  const imageUrl = useMemo(() => {
    if (previewUrl) return previewUrl
    return rawImageUrl
  }, [previewUrl, rawImageUrl])

  useEffect(() => {
    setHeroPos("50% 38%")
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

  if (query.isLoading)
    return (
      <Layout>
        <div className="flex min-h-[60vh] items-center justify-center">
          <span className="h-12 w-12 animate-spin rounded-full border-4 border-[color:rgba(148,163,184,0.35)] border-t-[color:var(--nav-link)]" />
        </div>
      </Layout>
    )

  if (query.isError || !query.data)
    return (
      <Layout>
        <div className="px-4 py-10">
          <p className="text-lg font-semibold text-red-500">{t("news:states.loadError")}</p>
        </div>
      </Layout>
    )

  return (
    <Layout>
      <section className="w-full bg-[color:var(--page-bg)]">
        <div className="relative mx-auto w-full max-w-6xl px-4 pb-16 pt-6 sm:px-8 lg:px-14">
          <div className="mb-6 flex justify-start">
            <Button
              variant="outline"
              size="md"
              className="w-full sm:w-auto"
              onClick={handleBack}
              leadingIcon={<ArrowBackIcon fontSize="small" />}
            >
              {t("common:buttons.back")}
            </Button>
          </div>

          <article className="overflow-hidden rounded-ue-3xl border border-[color:color-mix(in_srgb,var(--page-border,rgba(148,163,184,0.32))_70%,transparent_30%)] bg-[color:color-mix(in_srgb,var(--page-bg,#fff)_92%,white_8%)] shadow-[0_35px_90px_rgba(15,23,42,0.18)]">
            <div className="relative h-[260px] w-full overflow-hidden bg-[color:color-mix(in_srgb,var(--dash-card-news-orb,#1d4ed8)_18%,transparent_82%)] sm:h-[320px]">
              <SmartImage
                srcRaw={imageUrl}
                alt={
                  displayTitle
                    ? t("news:alt.hero", { title: displayTitle })
                    : t("news:alt.heroFallback")
                }
                onLoad={handleHeroLoad}
                style={{
                  position: "absolute",
                  inset: 0,
                  width: "100%",
                  height: "100%",
                  display: "block",
                  objectFit: "cover",
                  objectPosition: heroPos,
                }}
              />
              <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(255,255,255,0.45),transparent_60%)]" aria-hidden />
            </div>

            <div className="px-6 py-8 sm:px-10 sm:py-10">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <h1 className="text-3xl font-black leading-tight text-[color:var(--page-text)] sm:text-[clamp(2.1rem,3.2vw,2.75rem)]">
                    {displayTitle}
                  </h1>
                  {createdAt && (
                    <div className="mt-3 text-sm font-semibold uppercase tracking-[0.18em] text-[color:color-mix(in_srgb,var(--secondary-text,#64748b)_70%,white_30%)]">
                      {t("news:meta.published")} {" "}
                      <time dateTime={createdAtIso}>{createdAtLabel}</time>
                    </div>
                  )}
                </div>

                {user?.role === "admin" && (
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      onClick={openEdit}
                      aria-label={t("news:aria.editNews") ?? undefined}
                      disabled={saving || deleting}
                      className={cn(
                        "inline-flex h-11 w-11 items-center justify-center rounded-full border border-[color:color-mix(in_srgb,var(--page-border,rgba(148,163,184,0.32))_70%,transparent_30%)] bg-[color:color-mix(in_srgb,white_88%,var(--page-bg)_12%)] text-[color:var(--page-text)] shadow-[0_14px_26px_rgba(15,23,42,0.12)] transition",
                        saving || deleting ? "opacity-50" : "hover:bg-[color:color-mix(in_srgb,var(--nav-link)_12%,white_88%)]",
                      )}
                    >
                      <EditIcon fontSize="small" />
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirmDeleteOpen(true)}
                      aria-label={t("news:aria.deleteNews") ?? undefined}
                      disabled={deleting || saving}
                      className={cn(
                        "inline-flex h-11 w-11 items-center justify-center rounded-full border border-[color:color-mix(in_srgb,var(--page-border,rgba(248,113,113,0.32))_60%,transparent_40%)] bg-red-50/80 text-red-500 shadow-[0_14px_26px_rgba(248,113,113,0.25)] transition",
                        deleting || saving ? "opacity-50" : "hover:bg-red-100",
                      )}
                    >
                      <DeleteIcon fontSize="small" />
                    </button>
                  </div>
                )}
              </div>

              <div className="mt-8 text-lg leading-relaxed text-[color:color-mix(in_srgb,var(--page-text)_92%,white_8%)] whitespace-pre-line">
                {content}
              </div>
            </div>
          </article>
        </div>
      </section>

      <Modal
        open={editOpen}
        onClose={closeEdit}
        labelledBy={editDialogTitleId}
        fullScreenOnMobile={isMobile}
        size="sm"
        panelClassName={cn(isMobile ? "rounded-none" : "")}
      >
        <ModalHeader titleId={editDialogTitleId}>{t("news:dialogs.edit.title")}</ModalHeader>
        <form
          className="flex h-full flex-col"
          onSubmit={(event) => {
            event.preventDefault()
            void handleSave()
          }}
        >
          <ModalBody>
            <div className="flex flex-col gap-4">
              <label htmlFor={editTitleId} className={modalFieldStyles.label}>
                {t("news:form.title")}
                <input
                  id={editTitleId}
                  type="text"
                  value={editData.title}
                  onChange={(e) => setEditData({ ...editData, title: e.target.value })}
                  className={modalFieldStyles.input}
                  disabled={saving}
                  required
                />
              </label>
              <label htmlFor={editContentId} className={modalFieldStyles.label}>
                {t("news:form.text")}
                <textarea
                  id={editContentId}
                  value={editData.content}
                  onChange={(e) => setEditData({ ...editData, content: e.target.value })}
                  className={modalFieldStyles.textarea}
                  disabled={saving}
                  required
                />
              </label>
              <label htmlFor={editTitleEnId} className={modalFieldStyles.label}>
                {t("news:form.title_en", { defaultValue: "Title (English)" })}
                <input
                  id={editTitleEnId}
                  type="text"
                  value={editData.title_en}
                  onChange={(e) => setEditData({ ...editData, title_en: e.target.value })}
                  className={modalFieldStyles.input}
                  disabled={saving}
                />
              </label>
              <label htmlFor={editContentEnId} className={modalFieldStyles.label}>
                {t("news:form.content_en", { defaultValue: "News text (English)" })}
                <textarea
                  id={editContentEnId}
                  value={editData.content_en}
                  onChange={(e) => setEditData({ ...editData, content_en: e.target.value })}
                  className={modalFieldStyles.textarea}
                  disabled={saving}
                />
              </label>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                <Button
                  as="label"
                  variant="outline"
                  size="md"
                  className="cursor-pointer"
                  leadingIcon={<PhotoCamera fontSize="small" />}
                  disabled={saving}
                >
                  {newImage ? t("news:form.changePhoto") : t("news:form.uploadPhoto")}
                  <input
                    id={editFileInputId}
                    ref={imageInputRef}
                    type="file"
                    accept="image/*"
                    hidden
                    onChange={handleImageChange}
                    disabled={saving}
                  />
                </Button>
                {imageUrl && (
                  <SmartImage
                    srcRaw={imageUrl}
                    alt={t("news:alt.preview")}
                    style={{
                      width: 148,
                      height: 90,
                      borderRadius: 18,
                      border: "1px solid rgba(148,163,184,0.32)",
                      boxShadow: "0 12px 28px rgba(15,23,42,0.16)",
                    }}
                  />
                )}
              </div>
            </div>
          </ModalBody>
          <ModalFooter>
            <Button
              type="button"
              variant="outline"
              onClick={closeEdit}
              disabled={saving}
            >
              {t("common:buttons.cancel")}
            </Button>
            <Button type="submit" loading={saving}>
              {t("common:buttons.save")}
            </Button>
          </ModalFooter>
        </form>
      </Modal>

      <Modal
        open={confirmDeleteOpen}
        onClose={() => setConfirmDeleteOpen(false)}
        labelledBy={deleteDialogTitleId}
        size="sm"
      >
        <ModalHeader titleId={deleteDialogTitleId}>{t("news:dialogs.delete.title")}</ModalHeader>
        <ModalBody>
          <p className="text-[color:color-mix(in_srgb,var(--secondary-text,#64748b)_90%,white_10%)]">
            {t("news:dialogs.delete.description")}
          </p>
        </ModalBody>
        <ModalFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => setConfirmDeleteOpen(false)}
            disabled={deleting}
          >
            {t("common:buttons.cancel")}
          </Button>
          <Button
            type="button"
            variant="solid"
            className="!bg-red-500 hover:!bg-red-600 focus-visible:!shadow-[0_0_0_3px_rgba(239,68,68,0.35)]"
            onClick={() => {
              void handleDelete()
            }}
            loading={deleting}
            leadingIcon={<DeleteIcon fontSize="small" />}
          >
            {t("common:buttons.delete")}
          </Button>
        </ModalFooter>
      </Modal>

      {snack && (
        <div className="pointer-events-none fixed bottom-8 left-1/2 z-[var(--ue-z-index-toast,2147483600)] w-[min(92vw,420px)] -translate-x-1/2">
          <div
            className="pointer-events-auto rounded-ue-xl border border-[color:color-mix(in_srgb,var(--page-border,rgba(148,163,184,0.32))_70%,transparent_30%)] bg-[color:color-mix(in_srgb,var(--page-bg,#fff)_94%,white_6%)] px-5 py-4 text-center text-sm font-semibold text-[color:color-mix(in_srgb,var(--page-text)_90%,white_10%)] shadow-[0_20px_55px_rgba(15,23,42,0.2)]"
            role="status"
            aria-live="polite"
          >
            <span>{snack}</span>
          </div>
        </div>
      )}
    </Layout>
  )
}
