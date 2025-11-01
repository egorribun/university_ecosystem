import { FC, memo, useState, useEffect, useRef, useCallback, useMemo, type SVGProps } from "react"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Button } from "@/components/ui/button"
import { TextArea, TextInput } from "@/components/ui/input"
import {
  Modal,
  ModalBody,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalTitle,
} from "@/components/ui/modal"
import { useAuth } from "../contexts/AuthContext"
import { useLanguage } from "@/contexts/LanguageContext"
import api from "../api/client"
import { useNavigate } from "react-router-dom"
import dayjs from "dayjs"
import utc from "dayjs/plugin/utc"
import timezone from "dayjs/plugin/timezone"
import SmartImage from "@/components/SmartImage"
import { cn } from "@/utils/cn"
import { sanitizeNewsText } from "@/utils/sanitize"
import { useTranslation } from "react-i18next"
import useMediaQuery from "@/hooks/useMediaQuery"

const DotsVerticalIcon = (props: SVGProps<SVGSVGElement>) => (
  <svg viewBox="0 0 20 20" fill="currentColor" aria-hidden focusable="false" {...props}>
    <path d="M10 4a1.5 1.5 0 110-3 1.5 1.5 0 010 3zm0 7a1.5 1.5 0 110-3 1.5 1.5 0 010 3zm0 7a1.5 1.5 0 110-3 1.5 1.5 0 010 3z" />
  </svg>
)

const PencilSquareIcon = (props: SVGProps<SVGSVGElement>) => (
  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden focusable="false" {...props}>
    <path d="M4 17.25V20h2.75l8.08-8.08-2.75-2.75L4 17.25zm13.71-9.04a1 1 0 000-1.41l-1.51-1.51a1 1 0 00-1.41 0l-1.34 1.34 2.75 2.75 1.51-1.17z" />
  </svg>
)

const TrashIcon = (props: SVGProps<SVGSVGElement>) => (
  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden focusable="false" {...props}>
    <path d="M9 3a1 1 0 00-1 1v1H4.5a1 1 0 000 2H5v11a3 3 0 003 3h8a3 3 0 003-3V7h.5a1 1 0 000-2H16V4a1 1 0 00-1-1H9zm1 2h4V4h-4v1zm-1 4a1 1 0 012 0v8a1 1 0 11-2 0V9zm6-1a1 1 0 00-1 1v8a1 1 0 102 0V9a1 1 0 00-1-1z" />
  </svg>
)

const CameraIcon = (props: SVGProps<SVGSVGElement>) => (
  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden focusable="false" {...props}>
    <path d="M9.5 4.5l-.72 1.44A1 1 0 017.89 6H6a3 3 0 00-3 3v8a3 3 0 003 3h12a3 3 0 003-3V9a3 3 0 00-3-3h-1.89a1 1 0 01-.89-.56L14.5 4.5h-5zm2.5 5.5a4 4 0 110 8 4 4 0 010-8zm0 2a2 2 0 100 4 2 2 0 000-4z" />
  </svg>
)

dayjs.extend(utc)
dayjs.extend(timezone)

type NewsCardProps = {
  id: number
  title: string
  content: string
  title_en?: string | null
  content_en?: string | null
  created_at: string
  image_url?: string
  onChange?: () => void
}

const getMoscowDate = (dateStr: string) => {
  let parsed = dayjs(dateStr)
  if (!/([Zz]|[+\-]\d\d:?\d\d)$/.test(dateStr)) {
    parsed = dayjs.utc(dateStr)
  }
  return parsed.tz("Europe/Moscow").format("DD.MM.YYYY HH:mm")
}

const NewsCardComponent: FC<NewsCardProps> = ({
  id,
  title,
  content,
  title_en,
  content_en,
  created_at,
  image_url,
  onChange,
}) => {
  const { user } = useAuth()
  const navigate = useNavigate()
  const { t } = useTranslation(["news", "common"])
  const { language } = useLanguage()

  const [menuOpen, setMenuOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false)

  const [editData, setEditData] = useState({
    title,
    content,
    title_en: title_en ?? "",
    content_en: content_en ?? "",
    image_url: image_url || "",
  })
  const [loading, setLoading] = useState(false)

  const [newImage, setNewImage] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [imageLoading, setImageLoading] = useState(false)
  const imageInputRef = useRef<HTMLInputElement>(null)
  const editTitleRef = useRef<HTMLInputElement>(null)
  const [cardImageReady, setCardImageReady] = useState(!image_url)

  const isMobile = useMediaQuery("(max-width:600px)")

  const localizedTitle = useMemo(() => {
    const english = title_en ?? ""
    if (language === "en" && english.trim()) return english
    return title || english
  }, [language, title, title_en])

  const localizedContent = useMemo(() => {
    const english = content_en ?? ""
    if (language === "en" && english.trim()) return english
    return content || english
  }, [language, content, content_en])

  const sanitizedPreview = useMemo(() => sanitizeNewsText(localizedContent), [localizedContent])
  const createdAtIso = useMemo(
    () => (created_at ? dayjs(created_at).toISOString() : ""),
    [created_at]
  )
  const createdAtLabel = useMemo(() => (created_at ? getMoscowDate(created_at) : ""), [created_at])
  const cardImageUrl = useMemo(() => image_url || "", [image_url])

  useEffect(() => {
    setCardImageReady(!cardImageUrl)
  }, [cardImageUrl])

  const handleCardImageReady = useCallback(() => setCardImageReady(true), [])

  // preview URL lifecycle
  useEffect(() => {
    if (!newImage) {
      setPreviewUrl(null)
      return
    }
    const url = URL.createObjectURL(newImage)
    setPreviewUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [newImage])

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl)
    }
  }, [previewUrl])

  const openEditDialog = useCallback(() => {
    setEditData({
      title,
      content,
      title_en: title_en ?? "",
      content_en: content_en ?? "",
      image_url: image_url || "",
    })
    setEditOpen(true)
    setNewImage(null)
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl)
      setPreviewUrl(null)
    }
    if (imageInputRef.current) imageInputRef.current.value = ""
  }, [title, content, title_en, content_en, image_url, previewUrl])

  const closeEditDialog = useCallback(() => {
    setEditOpen(false)
    setNewImage(null)
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl)
      setPreviewUrl(null)
    }
    if (imageInputRef.current) imageInputRef.current.value = ""
  }, [previewUrl])

  const handleEditOpenChange = useCallback(
    (open: boolean) => {
      if (!open) {
        closeEditDialog()
      }
    },
    [closeEditDialog]
  )

  const editImageUrl = useMemo(
    () => previewUrl || editData.image_url || "",
    [editData.image_url, previewUrl]
  )

  const handleImageChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) setNewImage(file)
  }, [])

  const handleEdit = useCallback(async () => {
    setLoading(true)
    try {
      let imgUrl = editData.image_url
      if (newImage) {
        setImageLoading(true)
        try {
          const data = new FormData()
          data.append("file", newImage)
          // единый эндпоинт загрузки
          const res = await api.post<{ url: string }>(`/news/upload_image`, data, {
            headers: { "Content-Type": "multipart/form-data" },
          })
          imgUrl = res.data.url
        } finally {
          setImageLoading(false)
        }
      }
      const payload = {
        title: editData.title,
        content: editData.content,
        title_en: editData.title_en,
        content_en: editData.content_en,
        image_url: imgUrl,
      }
      await api.patch(`/news/${id}`, payload)
      setEditData((prev) => ({ ...prev, image_url: imgUrl }))
      closeEditDialog()
      onChange && onChange()
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [closeEditDialog, editData, id, newImage, onChange])

  const handleDelete = useCallback(async () => {
    setLoading(true)
    try {
      await api.delete(`/news/${id}`)
      onChange && onChange()
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
      setConfirmDeleteOpen(false)
    }
  }, [id, onChange])

  const handleConfirmOpenChange = useCallback((open: boolean) => {
    setConfirmDeleteOpen(open)
  }, [])

  const handleCardClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (editOpen) {
        e.stopPropagation()
        e.preventDefault()
        return
      }
      const el = e.target as HTMLElement
      if (
        el.closest(
          "button, a, input, textarea, [role='menu'], [role='dialog'], [data-news-card-interactive='true']"
        )
      ) {
        return
      }
      navigate(`/news/${id}`)
    },
    [editOpen, id, navigate]
  )

  const hoveringDisabled = editOpen || menuOpen

  return (
    <div
      className={cn(
        "news-card relative flex w-full max-w-[700px] min-h-[340px] flex-col overflow-hidden rounded-[1.2rem] border border-[color:var(--glass-border)] bg-[color:var(--card-bg)] text-[color:var(--page-text)] shadow-surface transition-[transform,box-shadow] duration-200 ease-out focus-visible:outline-none focus-visible:shadow-[var(--ue-focus-ring)]",
        "motion-reduce:transition-[box-shadow]",
        hoveringDisabled
          ? "cursor-default"
          : "cursor-pointer hover:-translate-y-[2px] hover:scale-[1.02] hover:shadow-surface-strong active:scale-[0.997] motion-reduce:hover:translate-y-0 motion-reduce:hover:scale-100 motion-reduce:active:scale-100"
      )}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (editOpen || menuOpen) return
        if (e.currentTarget !== e.target) return
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault()
          navigate(`/news/${id}`)
        }
      }}
      onClick={handleCardClick}
    >
      {user?.role === "admin" ? (
        <DropdownMenu open={menuOpen} onOpenChange={setMenuOpen}>
          <DropdownMenuTrigger
            disabled={loading}
            onClick={(event) => {
              event.stopPropagation()
            }}
            onPointerDown={(event) => {
              event.stopPropagation()
            }}
            className="absolute right-3 top-3 z-10 flex h-10 w-10 items-center justify-center rounded-full border border-white/60 bg-white/90 text-[color:var(--nav-link)] shadow-surface transition-colors hover:bg-white focus-visible:shadow-[var(--ue-focus-ring)]"
            aria-label={t("news:aria.cardActions")}
            data-news-card-interactive="true"
          >
            <DotsVerticalIcon className="h-4 w-4" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="min-w-[11.5rem]">
            <DropdownMenuItem
              onClick={(event) => {
                event.stopPropagation()
                setMenuOpen(false)
                openEditDialog()
              }}
              className="text-sm font-semibold text-[color:var(--nav-text)]"
              data-news-card-interactive="true"
            >
              <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-[color:var(--nav-link)]/12 text-[color:var(--nav-link)]">
                <PencilSquareIcon className="h-4 w-4" />
              </span>
              <span>{t("common:buttons.edit")}</span>
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={(event) => {
                event.stopPropagation()
                setMenuOpen(false)
                setConfirmDeleteOpen(true)
              }}
              className="text-sm font-semibold text-[color:var(--badge-lab)]"
              data-news-card-interactive="true"
            >
              <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-[color:var(--badge-lab)]/12 text-[color:var(--badge-lab)]">
                <TrashIcon className="h-4 w-4" />
              </span>
              <span>{t("common:buttons.delete")}</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}

      <div
        className="relative h-[160px] w-full overflow-hidden border-b border-white/10 sm:h-[180px] md:h-[220px] lg:h-[240px]"
        style={{
          background: "linear-gradient(135deg, rgba(13,71,161,0.18), rgba(63,81,181,0.08))",
        }}
      >
        <SmartImage
          srcRaw={cardImageUrl}
          alt={
            localizedTitle
              ? t("news:alt.hero", { title: localizedTitle })
              : t("news:alt.heroFallback")
          }
          sizes="(min-width: 1200px) 640px, (min-width: 900px) 520px, 100vw"
          className="h-full w-full object-cover"
          onLoad={handleCardImageReady}
          onError={handleCardImageReady}
        />
        <span
          aria-hidden
          className={cn(
            "pointer-events-none absolute inset-0 bg-[linear-gradient(120deg,rgba(255,255,255,0.2),rgba(255,255,255,0.05))]",
            "transition-opacity duration-300 ease-out",
            cardImageReady ? "opacity-0" : "opacity-100"
          )}
        />
      </div>

      <div className="flex flex-1 flex-col gap-3 px-5 py-4 sm:px-7 sm:py-6">
        <h3 className="truncate font-display text-[clamp(1.07rem,3vw,1.18rem)] font-semibold text-[color:var(--page-text)]">
          {localizedTitle}
        </h3>
        <p className="line-clamp-3 min-h-[2.75rem] text-[clamp(0.99rem,2vw,1.06rem)] text-[color:var(--secondary-text)] sm:min-h-[4rem]">
          {sanitizedPreview}
        </p>
        <div className="mt-auto text-sm text-[color:var(--secondary-text)]">
          {createdAtIso ? <time dateTime={createdAtIso}>{createdAtLabel}</time> : null}
        </div>
      </div>

      <Modal
        open={editOpen}
        onOpenChange={handleEditOpenChange}
        closeOnOverlayClick={!loading && !imageLoading}
        closeOnEscape={!loading && !imageLoading}
        initialFocus={() => editTitleRef.current ?? undefined}
      >
        <ModalContent
          className={cn(
            "w-full max-w-2xl sm:max-w-xl",
            isMobile ? "h-[calc(100vh-2rem)] max-h-[calc(100vh-2rem)] rounded-[1.25rem]" : ""
          )}
        >
          <ModalHeader className="px-6 pt-6 pb-4">
            <ModalTitle className="text-xl font-semibold">
              {t("news:dialogs.edit.title")}
            </ModalTitle>
          </ModalHeader>
          <ModalBody className="flex flex-col gap-4 px-6 pb-2">
            <TextInput
              ref={editTitleRef}
              label={t("news:form.title")}
              value={editData.title}
              onChange={(e) => setEditData({ ...editData, title: e.target.value })}
            />
            <TextArea
              label={t("news:form.text")}
              value={editData.content}
              onChange={(e) => setEditData({ ...editData, content: e.target.value })}
              rows={4}
            />
            <TextInput
              label={t("news:form.title_en", { defaultValue: "Title (English)" })}
              value={editData.title_en}
              onChange={(e) => setEditData({ ...editData, title_en: e.target.value })}
            />
            <TextArea
              label={t("news:form.content_en", { defaultValue: "News text (English)" })}
              value={editData.content_en}
              onChange={(e) => setEditData({ ...editData, content_en: e.target.value })}
              rows={4}
            />
            <div className="flex flex-col gap-3">
              <Button
                type="button"
                variant="outline"
                leadingIcon={<CameraIcon className="h-4 w-4" />}
                className="w-fit"
                disabled={imageLoading}
                loading={imageLoading}
                onClick={() => {
                  if (imageLoading) return
                  imageInputRef.current?.click()
                }}
              >
                {imageLoading ? t("common:statuses.uploading") : t("news:form.changePhoto")}
              </Button>
              <input
                type="file"
                accept="image/*"
                ref={imageInputRef}
                onChange={handleImageChange}
                className="sr-only"
              />
              {editImageUrl ? (
                <div className="inline-flex overflow-hidden rounded-ue-md border border-[color:var(--glass-border)] bg-[color:var(--card-bg)]/90 p-1 shadow-surface">
                  <SmartImage
                    srcRaw={editImageUrl}
                    alt={t("news:alt.preview")}
                    className="h-[90px] w-[140px] rounded-[0.75rem] object-cover"
                  />
                </div>
              ) : null}
            </div>
          </ModalBody>
          <ModalFooter className="flex flex-col gap-3 px-6 pb-6 sm:flex-row sm:justify-end">
            <Button variant="solid" onClick={handleEdit} loading={loading} disabled={imageLoading}>
              {t("common:buttons.save")}
            </Button>
            <Button variant="outline" onClick={closeEditDialog} disabled={loading || imageLoading}>
              {t("common:buttons.cancel")}
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      <Modal
        open={confirmDeleteOpen}
        onOpenChange={handleConfirmOpenChange}
        closeOnOverlayClick={!loading}
        closeOnEscape={!loading}
      >
        <ModalContent className="w-full max-w-md">
          <ModalHeader className="px-6 pt-6">
            <ModalTitle className="text-lg font-semibold">
              {t("news:dialogs.delete.title")}
            </ModalTitle>
          </ModalHeader>
          <ModalBody className="px-6 pb-2 text-[color:var(--secondary-text)]">
            <p>{t("news:dialogs.delete.description")}</p>
          </ModalBody>
          <ModalFooter className="flex flex-col gap-3 px-6 pb-6 sm:flex-row sm:justify-end">
            <Button
              variant="outline"
              onClick={() => setConfirmDeleteOpen(false)}
              disabled={loading}
            >
              {t("common:buttons.cancel")}
            </Button>
            <Button
              variant="solid"
              onClick={handleDelete}
              loading={loading}
              leadingIcon={<TrashIcon className="h-4 w-4" />}
              className="bg-[color:var(--badge-lab)] text-white hover:bg-[color-mix(in_srgb,var(--badge-lab) 85%,#ffffff 15%)]"
            >
              {t("common:buttons.delete")}
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </div>
  )
}

const areNewsCardPropsEqual = (prev: NewsCardProps, next: NewsCardProps) =>
  prev.id === next.id &&
  prev.title === next.title &&
  prev.title_en === next.title_en &&
  prev.content === next.content &&
  prev.content_en === next.content_en &&
  prev.created_at === next.created_at &&
  prev.image_url === next.image_url &&
  prev.onChange === next.onChange

export default memo(NewsCardComponent, areNewsCardPropsEqual)
