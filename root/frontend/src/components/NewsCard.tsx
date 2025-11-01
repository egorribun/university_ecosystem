import {
  FC,
  memo,
  useState,
  useEffect,
  useRef,
  useCallback,
  useMemo,
  useId,
} from "react"
import MoreVertIcon from "@mui/icons-material/MoreVert"
import EditIcon from "@mui/icons-material/Edit"
import DeleteIcon from "@mui/icons-material/Delete"
import PhotoCamera from "@mui/icons-material/PhotoCamera"
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
import { Button, Modal, ModalBody, ModalFooter, ModalHeader, modalFieldStyles } from "@/components/ui"

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
  const [cardImageReady, setCardImageReady] = useState(!image_url)

  const isMobile = useMediaQuery("(max-width: 640px)")
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  const editDialogTitleId = useId()
  const deleteDialogTitleId = useId()
  const editTitleId = useId()
  const editContentId = useId()
  const editTitleEnId = useId()
  const editContentEnId = useId()
  const editFileInputId = useId()

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
    [created_at],
  )
  const createdAtLabel = useMemo(() => (created_at ? getMoscowDate(created_at) : ""), [created_at])
  const cardImageUrl = useMemo(() => image_url || "", [image_url])

  useEffect(() => {
    setCardImageReady(!cardImageUrl)
  }, [cardImageUrl])

  const handleCardImageReady = useCallback(() => setCardImageReady(true), [])

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

  const closeMenu = useCallback(() => setMenuOpen(false), [])

  useEffect(() => {
    if (!menuOpen) return
    const handleClick = (event: MouseEvent | TouchEvent) => {
      const target = event.target as Node | null
      if (menuButtonRef.current?.contains(target)) return
      if (menuRef.current?.contains(target)) return
      setMenuOpen(false)
    }
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false)
      }
    }
    window.addEventListener("mousedown", handleClick)
    window.addEventListener("touchstart", handleClick)
    window.addEventListener("keydown", handleKey)
    return () => {
      window.removeEventListener("mousedown", handleClick)
      window.removeEventListener("touchstart", handleClick)
      window.removeEventListener("keydown", handleKey)
    }
  }, [menuOpen])

  const openEditDialog = useCallback(() => {
    setEditData({
      title,
      content,
      title_en: title_en ?? "",
      content_en: content_en ?? "",
      image_url: image_url || "",
    })
    setEditOpen(true)
    setMenuOpen(false)
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

  const editImageUrl = useMemo(
    () => previewUrl || editData.image_url || "",
    [editData.image_url, previewUrl],
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

  const handleCardClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (editOpen) {
        e.stopPropagation()
        e.preventDefault()
        return
      }
      const el = e.target as HTMLElement
      if (el.closest("button") || el.closest("input") || el.closest("[role='menu']")) return
      navigate(`/news/${id}`)
    },
    [editOpen, id, navigate],
  )

  const hoveringDisabled = editOpen || menuOpen
  const cardClasses = cn(
    "group relative flex h-full w-full max-w-[700px] flex-col overflow-hidden rounded-ue-2xl border border-[color:color-mix(in_srgb,var(--card-border,rgba(148,163,184,0.35))_70%,transparent_30%)] bg-[color:color-mix(in_srgb,var(--card-bg,var(--page-bg,#fff))_90%,white_10%)] text-[color:var(--page-text)] shadow-[0_22px_55px_rgba(15,23,42,0.14)] transition-[transform,box-shadow] duration-300 ease-out focus-visible:outline-none focus-visible:shadow-focus",
    hoveringDisabled
      ? "cursor-default"
      : "cursor-pointer hover:-translate-y-1.5 hover:shadow-[0_30px_70px_rgba(15,23,42,0.18)] active:scale-[0.995]",
    "motion-reduce:transition-none motion-reduce:hover:translate-y-0 motion-reduce:hover:shadow-none",
  )

  return (
    <article
      className={cardClasses}
      role="button"
      tabIndex={0}
      onClick={handleCardClick}
      onKeyDown={(e) => {
        if (editOpen) return
        if (e.currentTarget !== e.target) return
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault()
          navigate(`/news/${id}`)
        }
      }}
    >
      {user?.role === "admin" && (
        <>
          <button
            ref={menuButtonRef}
            type="button"
            className={cn(
              "absolute right-3 top-3 z-20 inline-flex h-10 w-10 items-center justify-center rounded-full border border-[color:color-mix(in_srgb,var(--page-border,rgba(148,163,184,0.35))_60%,transparent_40%)] bg-[color:color-mix(in_srgb,white_88%,var(--page-bg)_12%)] text-[color:var(--page-text)] shadow-[0_12px_25px_rgba(15,23,42,0.12)] transition",
              loading ? "pointer-events-none opacity-60" : "hover:bg-[color:color-mix(in_srgb,var(--nav-link)_12%,white_88%)]",
            )}
            aria-haspopup="menu"
            aria-expanded={menuOpen ? "true" : "false"}
            aria-label={t("news:aria.cardActions")}
            onClick={(event) => {
              event.stopPropagation()
              setMenuOpen((prev) => !prev)
            }}
            disabled={loading}
          >
            <MoreVertIcon fontSize="small" />
          </button>
          {menuOpen && (
            <div
              ref={menuRef}
              role="menu"
              aria-label={t("news:aria.cardActions") ?? undefined}
              className="absolute right-3 top-14 z-30 w-48 rounded-ue-xl border border-[color:color-mix(in_srgb,var(--page-border,rgba(148,163,184,0.3))_65%,transparent_35%)] bg-[color:color-mix(in_srgb,var(--page-bg,#fff)_92%,white_8%)] p-2 shadow-[0_24px_45px_rgba(15,23,42,0.2)]"
            >
              <button
                type="button"
                role="menuitem"
                className="flex w-full items-center gap-2 rounded-ue-lg px-3 py-2 text-sm font-semibold text-[color:var(--page-text)] transition hover:bg-[color:color-mix(in_srgb,var(--nav-link)_12%,transparent_88%)]"
                onClick={(e) => {
                  e.stopPropagation()
                  openEditDialog()
                }}
              >
                <EditIcon fontSize="small" />
                {t("common:buttons.edit")}
              </button>
              <button
                type="button"
                role="menuitem"
                className="mt-1 flex w-full items-center gap-2 rounded-ue-lg px-3 py-2 text-sm font-semibold text-red-500 transition hover:bg-red-500/10"
                onClick={(e) => {
                  e.stopPropagation()
                  setConfirmDeleteOpen(true)
                  closeMenu()
                }}
              >
                <DeleteIcon fontSize="small" />
                {t("common:buttons.delete")}
              </button>
            </div>
          )}
        </>
      )}

      <div className="relative h-[180px] w-full overflow-hidden bg-[color:color-mix(in_srgb,var(--dash-card-news-orb,#1d4ed8)_18%,transparent_82%)] sm:h-[210px]">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_15%_20%,rgba(255,255,255,0.45),transparent_60%)]" aria-hidden />
        <SmartImage
          srcRaw={cardImageUrl}
          alt={
            localizedTitle
              ? t("news:alt.hero", { title: localizedTitle })
              : t("news:alt.heroFallback")
          }
          sizes="(min-width: 1200px) 640px, (min-width: 900px) 520px, 100vw"
          style={{ width: "100%", height: "100%", display: "block", objectFit: "cover" }}
          onLoad={handleCardImageReady}
          onError={handleCardImageReady}
        />
        {!cardImageReady && (
          <div className="absolute inset-0 animate-pulse bg-[color:rgba(148,163,184,0.25)]" aria-hidden />
        )}
      </div>

      <div className="flex flex-1 flex-col px-6 pb-6 pt-5">
        <h3
          className="mb-2 text-lg font-bold leading-tight text-[color:var(--page-text)]"
          style={{
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
          }}
        >
          {localizedTitle}
        </h3>
        <p
          className="mb-4 text-sm font-medium text-[color:color-mix(in_srgb,var(--secondary-text,#64748b)_90%,white_10%)]"
          style={{
            display: "-webkit-box",
            WebkitLineClamp: 3,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
          }}
        >
          {sanitizedPreview}
        </p>
        <div className="mt-auto pt-2 text-xs font-semibold uppercase tracking-[0.18em] text-[color:color-mix(in_srgb,var(--secondary-text,#64748b)_70%,white_30%)]">
          {createdAtIso && <time dateTime={createdAtIso}>{createdAtLabel}</time>}
        </div>
      </div>

      <Modal
        open={editOpen}
        onClose={closeEditDialog}
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
            void handleEdit()
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
                  disabled={loading}
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
                  disabled={loading}
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
                  disabled={loading}
                />
              </label>
              <label htmlFor={editContentEnId} className={modalFieldStyles.label}>
                {t("news:form.content_en", { defaultValue: "News text (English)" })}
                <textarea
                  id={editContentEnId}
                  value={editData.content_en}
                  onChange={(e) => setEditData({ ...editData, content_en: e.target.value })}
                  className={modalFieldStyles.textarea}
                  disabled={loading}
                />
              </label>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                <Button
                  as="label"
                  variant="outline"
                  size="md"
                  className="cursor-pointer"
                  leadingIcon={<PhotoCamera fontSize="small" />}
                  disabled={loading || imageLoading}
                >
                  {imageLoading
                    ? t("common:statuses.uploading")
                    : t("news:form.changePhoto")}
                  <input
                    id={editFileInputId}
                    ref={imageInputRef}
                    type="file"
                    accept="image/*"
                    hidden
                    onChange={handleImageChange}
                    disabled={loading || imageLoading}
                  />
                </Button>
                {editImageUrl && (
                  <SmartImage
                    srcRaw={editImageUrl}
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
              onClick={closeEditDialog}
              disabled={loading || imageLoading}
            >
              {t("common:buttons.cancel")}
            </Button>
            <Button
              type="submit"
              loading={loading || imageLoading}
              disabled={imageLoading}
            >
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
            disabled={loading}
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
            loading={loading}
            leadingIcon={<DeleteIcon fontSize="small" />}
          >
            {t("common:buttons.delete")}
          </Button>
        </ModalFooter>
      </Modal>
    </article>
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
