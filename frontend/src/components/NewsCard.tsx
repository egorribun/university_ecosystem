import { FC, memo, useState, useEffect, useRef, useCallback, useMemo, type ReactNode } from "react"
import { motion } from "framer-motion"
import MoreVertIcon from "@mui/icons-material/MoreVert"
import EditIcon from "@mui/icons-material/Edit"
import DeleteIcon from "@mui/icons-material/Delete"
import PhotoCamera from "@mui/icons-material/PhotoCamera"
import ArrowOutwardIcon from "@mui/icons-material/ArrowOutward"
import ArticleIcon from "@mui/icons-material/Article"
import FavoriteIcon from "@mui/icons-material/Favorite"
import FavoriteBorderIcon from "@mui/icons-material/FavoriteBorder"
import ChatBubbleOutlineIcon from "@mui/icons-material/ChatBubbleOutline"
import { useNewsInteraction } from "@/hooks/useNewsInteraction"
import { useAuth } from "../contexts/AuthContext"
import { useLanguage } from "@/contexts/LanguageContext"
import { useOnlineStatus } from "@/hooks/useOnlineStatus"
import CloudDoneIcon from "@mui/icons-material/CloudDone"
import api from "../api/client"
import { useNavigate } from "react-router-dom"
import dayjs from "dayjs"
import utc from "dayjs/plugin/utc"
import timezone from "dayjs/plugin/timezone"
import SmartImage from "@/components/SmartImage"
import { cn } from "@/utils/cn"
import { sanitizeNewsText } from "@/utils/sanitize"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui"
import Dialog from "@/components/Dialog"

dayjs.extend(utc)
dayjs.extend(timezone)

const inputClass =
  "w-full rounded-ue-lg border border-white/12 bg-[color:color-mix(in_srgb,var(--card-bg)_94%,white_6%)] px-4 py-2.5 text-[0.98rem] text-[color:var(--page-text)] shadow-[inset_0_1px_0_rgba(15,23,42,0.08)] transition focus:border-[color:var(--nav-link)] focus:outline-none focus:shadow-focus placeholder:text-[color:var(--placeholder-fg)]"
const textareaClass = `${inputClass} min-h-[128px] resize-y leading-relaxed`

const iconButtonClass =
  "inline-flex h-9 w-9 items-center justify-center rounded-full border border-white/15 bg-white/80 text-[color:var(--nav-link)] shadow-surface transition hover:bg-white focus-visible:outline-none focus-visible:shadow-focus"

const menuPanelClass =
  "absolute right-0 top-12 z-20 min-w-[180px] overflow-hidden rounded-ue-md border border-white/12 bg-[color:color-mix(in_srgb,var(--card-bg)_94%,white_6%)]/98 shadow-surface-strong backdrop-blur-xl"

const menuItemClass =
  "flex w-full items-center gap-2 px-4 py-2.5 text-left text-[0.95rem] font-medium text-[color:var(--page-text)] transition hover:bg-[color:var(--glass-bg)]/80 focus-visible:outline-none focus-visible:bg-[color:var(--glass-bg)]"

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

type FieldProps = {
  label: string
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
  const isOnline = useOnlineStatus()
  const menuButtonRef = useRef<HTMLButtonElement | null>(null)
  const menuRef = useRef<HTMLDivElement | null>(null)
  const firstMenuItemRef = useRef<HTMLButtonElement | null>(null)
  const [editOpen, setEditOpen] = useState(false)
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false)
  const editTitleRef = useRef<HTMLInputElement | null>(null)

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

  const { interactions, toggleLike } = useNewsInteraction(id)
  const likesCount = interactions?.likes_count ?? 0
  const isLiked = interactions?.is_liked ?? false
  const commentsCount = interactions?.comments?.length ?? 0

  const menuId = `news-card-menu-${id}`
  const menuButtonId = `${menuId}-button`

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

  useEffect(() => {
    if (!menuOpen) return

    const handleClick = (event: MouseEvent) => {
      const target = event.target as Node
      if (menuRef.current?.contains(target) || menuButtonRef.current?.contains(target)) return
      setMenuOpen(false)
    }

    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false)
        menuButtonRef.current?.focus()
      }
    }

    document.addEventListener("mousedown", handleClick)
    document.addEventListener("keydown", handleKey)
    if (firstMenuItemRef.current) firstMenuItemRef.current.focus()

    return () => {
      document.removeEventListener("mousedown", handleClick)
      document.removeEventListener("keydown", handleKey)
    }
  }, [menuOpen])

  const closeMenu = useCallback(() => setMenuOpen(false), [])

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
    closeMenu()
  }, [title, content, title_en, content_en, image_url, previewUrl, closeMenu])

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

  const handleCardClick = useCallback(() => {
    if (editOpen) return
    navigate(`/news/${id}`)
  }, [editOpen, id, navigate])

  const hoveringDisabled = editOpen || menuOpen

  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -4 }}
      transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      className={cn(
        "card-glass group relative flex flex-col transition-[box-shadow] duration-300 ease-out h-[320px] md:h-[480px] w-full transform-gpu",
        hoveringDisabled
          ? "cursor-default"
          : "cursor-pointer hover:shadow-glass-strong active:scale-[0.985]"
      )}
      style={{ width: "100%" }}
    >
      {user?.role === "admin" && (
        <div className="absolute right-3 top-3 z-10">
          <button
            ref={menuButtonRef}
            type="button"
            id={menuButtonId}
            aria-label={t("news:aria.cardActions") ?? ""}
            aria-controls={menuOpen ? menuId : undefined}
            aria-haspopup="true"
            aria-expanded={menuOpen ? "true" : undefined}
            className={iconButtonClass}
            onClick={(event) => {
              event.stopPropagation()
              setMenuOpen((open) => !open)
            }}
            disabled={loading}
            data-news-card-menu-button
          >
            <MoreVertIcon fontSize="small" />
          </button>
          {menuOpen ? (
            <div
              ref={menuRef}
              id={menuId}
              role="menu"
              aria-labelledby={menuButtonId}
              data-news-card-menu
              className={menuPanelClass}
            >
              <button
                ref={firstMenuItemRef}
                type="button"
                className={menuItemClass}
                onClick={(event) => {
                  event.stopPropagation()
                  openEditDialog()
                }}
              >
                <EditIcon fontSize="small" className="text-[color:var(--nav-link)]" />
                {t("common:buttons.edit")}
              </button>
              <button
                type="button"
                className={cn(menuItemClass, "text-[#e11d48]")}
                onClick={(event) => {
                  event.stopPropagation()
                  setConfirmDeleteOpen(true)
                  closeMenu()
                }}
              >
                <DeleteIcon fontSize="small" className="text-[#e11d48]" />
                {t("common:buttons.delete")}
              </button>
            </div>
          ) : null}
        </div>
      )}

      <button
        type="button"
        onClick={handleCardClick}
        disabled={hoveringDisabled}
        className="group/button relative flex h-full flex-1 flex-col text-left focus-visible:outline-none disabled:cursor-default disabled:opacity-100"
      >
        <div className="relative w-full overflow-hidden border-b border-white/10 bg-[linear-gradient(135deg,rgba(29,78,216,0.18),rgba(59,130,246,0.08))]">
          <div
            className={cn(
              "absolute inset-0 animate-pulse bg-[color:color-mix(in_srgb,var(--glass-bg)_70%,white_30%)] transition-opacity duration-300",
              cardImageReady ? "opacity-0" : "opacity-100"
            )}
            aria-hidden
          />
          {cardImageUrl ? (
            <>
              <SmartImage
                srcRaw={cardImageUrl}
                alt={
                  localizedTitle
                    ? t("news:alt.hero", { title: localizedTitle })
                    : t("news:alt.heroFallback")
                }
                sizes="(min-width: 1200px) 640px, (min-width: 900px) 520px, 100vw"
                className="relative h-[120px] w-full object-cover transition duration-700 ease-out md:h-[220px]"
                onLoad={handleCardImageReady}
                onError={handleCardImageReady}
              />
              <div
                className="pointer-events-none absolute inset-0 z-[1] bg-[linear-gradient(180deg,rgba(15,23,42,0)_30%,rgba(15,23,42,0.75)_95%)] opacity-100"
                aria-hidden
              />
            </>
          ) : (
            <div className="flex h-[120px] w-full items-center justify-center bg-glass/70 text-white/70 md:h-[220px]">
              <ArticleIcon className="h-12 w-12" fontSize="large" />
            </div>
          )}
          {createdAtIso ? (
            <time
              dateTime={createdAtIso}
              className="absolute bottom-3 left-3 z-[2] rounded-ue-pill bg-black/60 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-white/90 transition duration-300 ease-out group-hover/button:translate-y-[-2px] group-hover/button:bg-black/70"
            >
              {createdAtLabel}
            </time>
          ) : null}
          {!isOnline && (
            <div className="absolute top-3 left-3 z-[2] flex items-center gap-1 rounded-ue-pill bg-amber-500/90 px-2 py-0.5 text-[0.65rem] font-bold uppercase tracking-wider text-amber-950 shadow-surface backdrop-blur-sm">
              <CloudDoneIcon sx={{ fontSize: 12 }} />
              <span>{t("common:statuses.cached", { defaultValue: "Кэш" })}</span>
            </div>
          )}
        </div>

        <div className="flex flex-1 flex-col gap-2 px-3 py-3 transition duration-300 ease-out group-hover:translate-y-[-1px] group-focus-visible/button:translate-y-[-1px] md:gap-3 md:px-5 md:py-6">
          <h3 className="truncate text-[clamp(1.07rem,3vw,1.18rem)] font-semibold">
            {localizedTitle}
          </h3>

          <p className="min-h-[48px] text-[clamp(0.88rem,2vw,1.08rem)] text-[color:var(--secondary-text)] line-clamp-2 md:min-h-[72px] md:line-clamp-3">
            {sanitizedPreview}
          </p>

          <div className="flex items-center gap-4 mt-1 border-t border-white/5 pt-3">
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                toggleLike()
              }}
              className={cn(
                "flex items-center gap-1.5 transition-colors duration-200",
                isLiked ? "text-rose-500" : "text-[color:var(--secondary-text)] hover:text-rose-400"
              )}
            >
              {isLiked ? (
                <FavoriteIcon fontSize="small" />
              ) : (
                <FavoriteBorderIcon fontSize="small" />
              )}
              <span className="text-xs font-bold tabular-nums">{likesCount}</span>
            </button>

            <div className="flex items-center gap-1.5 text-[color:var(--secondary-text)]">
              <ChatBubbleOutlineIcon fontSize="small" />
              <span className="text-xs font-bold tabular-nums">{commentsCount}</span>
            </div>
          </div>

          <div className="mt-auto flex items-center gap-2 pt-2 text-[color:var(--nav-link)]">
            <span className="translate-y-1 text-sm font-semibold tracking-wide opacity-0 transition duration-300 ease-out group-focus-visible/button:translate-y-0 group-focus-visible/button:opacity-100 group-hover:translate-y-0 group-hover:opacity-100">
              {t("common:cta.learnMore", { defaultValue: "Подробнее" })}
            </span>
            <ArrowOutwardIcon
              fontSize="small"
              className="translate-x-0 text-[color:var(--nav-link)] opacity-0 transition duration-300 ease-out group-focus-visible/button:translate-x-1 group-focus-visible/button:opacity-100 group-hover:translate-x-1 group-hover:opacity-100"
            />
          </div>
        </div>
      </button>

      <Dialog
        open={editOpen}
        onClose={closeEditDialog}
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
              onClick={closeEditDialog}
              disabled={loading || imageLoading}
              className="w-full sm:w-auto"
            >
              {t("common:buttons.cancel")}
            </Button>
            <Button
              onClick={() => {
                void handleEdit()
              }}
              disabled={loading || imageLoading}
              loading={loading}
              className="w-full sm:w-auto"
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
            void handleEdit()
          }}
        >
          <Field label={t("news:form.title") ?? ""} htmlFor={`news-edit-title-${id}`} required>
            <input
              id={`news-edit-title-${id}`}
              ref={editTitleRef}
              type="text"
              value={editData.title}
              onChange={(e) => setEditData({ ...editData, title: e.target.value })}
              className={inputClass}
            />
          </Field>

          <Field label={t("news:form.text") ?? ""} htmlFor={`news-edit-content-${id}`} required>
            <textarea
              id={`news-edit-content-${id}`}
              value={editData.content}
              onChange={(e) => setEditData({ ...editData, content: e.target.value })}
              className={textareaClass}
              rows={4}
            />
          </Field>

          <Field
            label={t("news:form.title_en", { defaultValue: "Title (English)" }) ?? ""}
            htmlFor={`news-edit-title-en-${id}`}
          >
            <input
              id={`news-edit-title-en-${id}`}
              type="text"
              value={editData.title_en}
              onChange={(e) => setEditData({ ...editData, title_en: e.target.value })}
              className={inputClass}
            />
          </Field>

          <Field
            label={t("news:form.content_en", { defaultValue: "News text (English)" }) ?? ""}
            htmlFor={`news-edit-content-en-${id}`}
          >
            <textarea
              id={`news-edit-content-en-${id}`}
              value={editData.content_en}
              onChange={(e) => setEditData({ ...editData, content_en: e.target.value })}
              className={textareaClass}
              rows={4}
            />
          </Field>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <Button
              as="label"
              variant="outline"
              size="sm"
              leadingIcon={<PhotoCamera className="text-[1.15rem]" />}
              className="w-full sm:w-auto"
              disabled={imageLoading}
            >
              {imageLoading ? t("common:statuses.uploading") : t("news:form.changePhoto")}
              <input
                type="file"
                accept="image/*"
                hidden
                ref={imageInputRef}
                onChange={handleImageChange}
              />
            </Button>

            {editImageUrl ? (
              <SmartImage
                srcRaw={editImageUrl}
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
              disabled={loading}
              className="w-full sm:w-auto"
            >
              {t("common:buttons.cancel")}
            </Button>
            <Button
              onClick={() => {
                void handleDelete()
              }}
              disabled={loading}
              loading={loading}
              className="w-full bg-[linear-gradient(98deg,#dc2626,#b91c1c)] text-white hover:bg-[linear-gradient(98deg,#b91c1c,#991b1b)] sm:w-auto"
            >
              <DeleteIcon fontSize="small" className="mr-1" />
              {t("common:buttons.delete")}
            </Button>
          </>
        }
      >
        <p className="text-[0.98rem] text-[color:var(--secondary-text)]">
          {t("news:dialogs.delete.description")}
        </p>
      </Dialog>
    </motion.article>
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
