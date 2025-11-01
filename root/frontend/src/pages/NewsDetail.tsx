import type React from "react"
import { useEffect, useMemo, useRef, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import dayjs from "dayjs"
import utc from "dayjs/plugin/utc"
import timezone from "dayjs/plugin/timezone"
import { deleteNews, fetchNewsItem, updateNews, uploadNewsImage, type NewsItem } from "@/api/news"
import Layout from "@/components/Layout"
import SmartImage from "@/components/SmartImage"
import {
  Button,
  IconButton,
  Modal,
  ModalBody,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalTitle,
  TextArea,
  TextInput,
  Toast,
  ToastViewport,
} from "@/components/ui"
import { useAuth } from "@/contexts/AuthContext"
import { useLanguage } from "@/contexts/LanguageContext"
import { useTranslation } from "react-i18next"
import useMediaQuery from "@/hooks/useMediaQuery"
import { cn } from "@/utils/cn"

type ToastIntent = Parameters<typeof Toast>[0] extends { intent?: infer I }
  ? NonNullable<I>
  : "info"

type ToastState = {
  id: number
  message: string
  intent: ToastIntent
}

type IconProps = React.SVGProps<SVGSVGElement> & { className?: string }

const SvgIcon = ({ className, ...rest }: IconProps) => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={1.8}
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden
    className={cn("h-5 w-5", className)}
    {...rest}
  />
)

const ArrowLeftIcon = (props: IconProps) => (
  <SvgIcon {...props}>
    <path d="M10.5 19.5 3 12l7.5-7.5" />
    <path d="M3 12h18" />
  </SvgIcon>
)

const PencilIcon = (props: IconProps) => (
  <SvgIcon {...props}>
    <path d="m4.75 19.25 1.92-6.73 8.8-8.79a1.78 1.78 0 0 1 2.51 0l1.54 1.54a1.78 1.78 0 0 1 0 2.51l-8.8 8.8z" />
    <path d="m12.38 6.62 4.5 4.5" />
  </SvgIcon>
)

const TrashIcon = (props: IconProps) => (
  <SvgIcon {...props}>
    <path d="M5 7h14" />
    <path d="M19 7v11.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 5 18.5V7" />
    <path d="m9.5 7 1-2.5h3L14.5 7" />
    <path d="M10 12v5" />
    <path d="M14 12v5" />
  </SvgIcon>
)

const CheckIcon = (props: IconProps) => (
  <SvgIcon {...props}>
    <path d="m5.5 12.5 4 4 9-9" />
  </SvgIcon>
)

const CloseIcon = (props: IconProps) => (
  <SvgIcon {...props}>
    <path d="m7 7 10 10M17 7 7 17" />
  </SvgIcon>
)

const CameraIcon = (props: IconProps) => (
  <SvgIcon {...props}>
    <path d="M3.5 8.5a2 2 0 0 1 2-2h2l1.1-1.8A2 2 0 0 1 9.5 4h5a2 2 0 0 1 1.7.9L17.3 6.5h2.2a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2h-14a2 2 0 0 1-2-2z" />
    <circle cx={12} cy={13} r={3.2} />
  </SvgIcon>
)

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
  const isMobile = useMediaQuery("(max-width:600px)")

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
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [toastState, setToastState] = useState<ToastState | null>(null)
  const [toastOpen, setToastOpen] = useState(false)
  const imageInputRef = useRef<HTMLInputElement>(null)
  const [heroPos, setHeroPos] = useState<"50% 18%" | "50% 38%" | "50% 50%" | string>("50% 38%")

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

  const resetPreview = () => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl)
      setPreviewUrl(null)
    }
    if (imageInputRef.current) imageInputRef.current.value = ""
    setNewImage(null)
  }

  const showToast = (message: string, intent: ToastIntent = "info") => {
    setToastState({ id: Date.now(), message, intent })
    setToastOpen(true)
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
    setErrors({})
    setEditOpen(true)
  }

  const closeEdit = () => {
    resetPreview()
    setErrors({})
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
    const nextErrors: Record<string, string> = {}
    if (!editData.title.trim()) {
      nextErrors.title = t("news:form.validation.titleRequired", {
        defaultValue: "Title is required",
      })
    }
    if (!editData.content.trim()) {
      nextErrors.content = t("news:form.validation.contentRequired", {
        defaultValue: "Content is required",
      })
    }
    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors)
      return
    }
    setErrors({})
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
  const heroAlt = displayTitle
    ? t("news:alt.hero", { title: displayTitle })
    : t("news:alt.heroFallback")

  if (query.isLoading)
    return (
      <Layout>
        <div className="grid min-h-[60vh] place-items-center">
          <span className="h-12 w-12 animate-spin rounded-full border-2 border-[color:rgba(148,163,184,0.38)] border-t-[color:var(--nav-link)]" />
        </div>
      </Layout>
    )

  if (query.isError || !query.data)
    return (
      <Layout>
        <div className="px-4 py-6 sm:px-6 md:px-10">
          <p className="text-base font-semibold text-[color:var(--badge-lab)]">
            {t("news:states.loadError")}
          </p>
        </div>
      </Layout>
    )

  return (
    <Layout>
      <div className="flex w-full justify-center bg-transparent">
        <div className="flex w-full max-w-5xl flex-col px-4 pb-16 pt-6 sm:px-6 md:px-10 lg:px-16">
          <div className="mb-6 flex w-full flex-col gap-4">
            <Button
              onClick={handleBack}
              leadingIcon={<ArrowLeftIcon className="h-5 w-5" />}
              size="md"
              fullWidth={isMobile}
              className="self-start rounded-ue-xl px-5 py-3 text-[clamp(0.95rem,2.2vw,1.15rem)] font-semibold tracking-wide shadow-surface transition-transform duration-200 hover:-translate-y-[1px]"
            >
              {t("common:buttons.back")}
            </Button>

            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="flex min-w-0 flex-col gap-2">
                <h1 className="font-display text-[clamp(1.4rem,4vw,2.4rem)] font-bold leading-tight text-[color:var(--page-text)]">
                  {displayTitle}
                </h1>
                {createdAt ? (
                  <p className="text-sm text-[color:var(--secondary-text)]">
                    {t("news:meta.published")} <time dateTime={createdAtIso}>{createdAtLabel}</time>
                  </p>
                ) : null}
              </div>

              {user?.role === "admin" ? (
                <div className="flex items-center gap-2">
                  <IconButton
                    aria-label={t("news:aria.editNews")}
                    onClick={openEdit}
                    variant="soft"
                    disabled={saving || deleting}
                  >
                    <PencilIcon />
                  </IconButton>
                  <IconButton
                    aria-label={t("news:aria.deleteNews")}
                    onClick={() => setConfirmDeleteOpen(true)}
                    variant="soft"
                    className="text-[color:var(--badge-lab)] hover:text-[color:var(--badge-lab)]"
                    disabled={deleting || saving}
                  >
                    <TrashIcon />
                  </IconButton>
                </div>
              ) : null}
            </div>
          </div>

          <div className="flex flex-col gap-6">
            <div className="relative w-full overflow-hidden rounded-[min(2rem,calc(var(--ue-radius-lg,1rem)*1.6))] border border-[color:var(--glass-border)] bg-[color:var(--card-bg)]/60 shadow-surface">
              <div className="aspect-[16/9] w-full md:aspect-[21/9]">
                {imageUrl ? (
                  <SmartImage
                    srcRaw={imageUrl}
                    alt={heroAlt}
                    onLoad={handleHeroLoad}
                    style={{
                      width: "100%",
                      height: "100%",
                      objectFit: "cover",
                      objectPosition: heroPos,
                    }}
                  />
                ) : (
                  <div className="flex h-full w-full items-center justify-center bg-[color:rgba(148,163,184,0.12)] text-center text-sm font-semibold text-[color:var(--secondary-text)]">
                    {t("news:states.noImage")}
                  </div>
                )}
              </div>
            </div>

            <div className="h-px w-full bg-[color:var(--glass-border)]/70" aria-hidden />

            <article className="prose max-w-none text-[color:var(--page-text)] prose-headings:font-semibold prose-p:text-[clamp(1.05rem,2.3vw,1.22rem)] prose-p:leading-relaxed prose-img:rounded-xl">
              <p className="whitespace-pre-line text-[clamp(1.05rem,2.3vw,1.22rem)] leading-relaxed">
                {content}
              </p>
            </article>
          </div>
        </div>
      </div>

      {editOpen ? (
        <Modal
          open={editOpen}
          onOpenChange={(open) => {
            if (!open) closeEdit()
          }}
          closeOnOverlayClick={!saving}
          closeOnEscape={!saving}
        >
          <ModalContent
            hideScrollbars
            className={cn(
              "w-full max-w-3xl bg-[color:var(--card-bg)]/98",
              isMobile && "h-[min(95vh,720px)] max-w-full"
            )}
          >
            <ModalHeader className="gap-3">
              <ModalTitle className="text-[clamp(1.25rem,3vw,1.6rem)] font-semibold">
                {t("news:dialogs.edit.title")}
              </ModalTitle>
            </ModalHeader>
            <ModalBody className="gap-5">
              <TextInput
                label={t("news:form.title")}
                value={editData.title}
                onChange={(e) => {
                  setEditData({ ...editData, title: e.target.value })
                  if (errors.title) setErrors((prev) => ({ ...prev, title: "" }))
                }}
                required
                disabled={saving}
                errorText={errors.title || undefined}
              />
              <TextArea
                label={t("news:form.text")}
                value={editData.content}
                onChange={(e) => {
                  setEditData({ ...editData, content: e.target.value })
                  if (errors.content) setErrors((prev) => ({ ...prev, content: "" }))
                }}
                rows={5}
                required
                disabled={saving}
                errorText={errors.content || undefined}
              />
              <TextInput
                label={t("news:form.title_en", { defaultValue: "Title (English)" })}
                value={editData.title_en}
                onChange={(e) => setEditData({ ...editData, title_en: e.target.value })}
                disabled={saving}
              />
              <TextArea
                label={t("news:form.content_en", { defaultValue: "News text (English)" })}
                value={editData.content_en}
                onChange={(e) => setEditData({ ...editData, content_en: e.target.value })}
                rows={5}
                disabled={saving}
              />
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
                <Button
                  as="label"
                  variant="outline"
                  size="md"
                  leadingIcon={<CameraIcon />}
                  className="cursor-pointer whitespace-nowrap"
                  loading={saving}
                >
                  {newImage ? t("news:form.changePhoto") : t("news:form.uploadPhoto")}
                  <input
                    type="file"
                    accept="image/*"
                    ref={imageInputRef}
                    onChange={handleImageChange}
                    className="sr-only"
                    disabled={saving}
                  />
                </Button>
                {imageUrl ? (
                  <div className="h-24 w-full overflow-hidden rounded-xl border border-[color:var(--glass-border)] sm:h-24 sm:w-40">
                    <SmartImage
                      srcRaw={imageUrl}
                      alt={t("news:alt.preview")}
                      style={{ width: "100%", height: "100%", objectFit: "cover" }}
                    />
                  </div>
                ) : null}
              </div>
            </ModalBody>
            <ModalFooter className="gap-3 sm:flex-row">
              <Button
                variant="outline"
                size="md"
                className="sm:w-auto"
                onClick={closeEdit}
                disabled={saving}
                leadingIcon={<CloseIcon className="h-5 w-5" />}
              >
                {t("common:buttons.cancel")}
              </Button>
              <Button
                size="md"
                className="sm:w-auto"
                onClick={handleSave}
                loading={saving}
                leadingIcon={<CheckIcon className="h-5 w-5" />}
              >
                {t("common:buttons.save")}
              </Button>
            </ModalFooter>
          </ModalContent>
        </Modal>
      ) : null}

      {confirmDeleteOpen ? (
        <Modal
          open={confirmDeleteOpen}
          onOpenChange={(open) => {
            if (!open) setConfirmDeleteOpen(false)
          }}
          closeOnOverlayClick={!deleting}
          closeOnEscape={!deleting}
        >
          <ModalContent
            className={cn("w-full max-w-md", isMobile && "h-[min(80vh,460px)] max-w-full")}
          >
            <ModalHeader>
              <ModalTitle>{t("news:dialogs.delete.title")}</ModalTitle>
            </ModalHeader>
            <ModalBody>
              <p className="text-sm leading-relaxed text-[color:var(--secondary-text)]">
                {t("news:dialogs.delete.description")}
              </p>
            </ModalBody>
            <ModalFooter className="gap-3 sm:flex-row">
              <Button
                variant="outline"
                onClick={() => setConfirmDeleteOpen(false)}
                disabled={deleting}
                leadingIcon={<CloseIcon className="h-5 w-5" />}
              >
                {t("common:buttons.cancel")}
              </Button>
              <Button
                onClick={handleDelete}
                loading={deleting}
                className="bg-[color:var(--badge-lab)] text-white hover:bg-[color:var(--badge-lab)]/90"
                leadingIcon={<TrashIcon className="h-5 w-5" />}
              >
                {t("common:buttons.delete")}
              </Button>
            </ModalFooter>
          </ModalContent>
        </Modal>
      ) : null}

      {toastState ? (
        <ToastViewport position="bottom-right">
          <Toast
            key={toastState.id}
            open={toastOpen}
            onOpenChange={(open) => {
              setToastOpen(open)
              if (!open) {
                setTimeout(() => setToastState(null), 150)
              }
            }}
            description={toastState.message}
            intent={toastState.intent}
            duration={2400}
          />
        </ToastViewport>
      ) : null}
    </Layout>
  )
}
