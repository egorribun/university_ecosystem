import { FC, memo, useState, useEffect, useRef, useCallback, useMemo } from "react"
import {
  Box,
  Typography,
  IconButton,
  Menu,
  MenuItem,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Stack,
  Button,
  useMediaQuery,
} from "@mui/material"
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
import { cardHoverStyles } from "@/constants/cardHover"
import { cn } from "@/utils/cn"
import { sanitizeNewsText } from "@/utils/sanitize"
import { useTranslation } from "react-i18next"

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

  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null)
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

  const isMobile = useMediaQuery("(max-width:600px)")
  const menuId = `news-card-menu-${id}`

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

  const handleCardClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (editOpen) {
        e.stopPropagation()
        e.preventDefault()
        return
      }
      const el = e.target as HTMLElement
      if (
        el.closest("button") ||
        el.closest("input") ||
        el.closest(".MuiInputBase-root") ||
        el.closest('[role="menu"]')
      )
        return
      navigate(`/news/${id}`)
    },
    [editOpen, id, navigate]
  )

  const hoveringDisabled = editOpen || Boolean(menuAnchor)
  const cardHover = cardHoverStyles({ disabled: hoveringDisabled })

  return (
    <Box
      className={cn("news-card", cardHover.className)}
      style={cardHover.style}
      sx={{
        width: "100%",
        maxWidth: 700,
        borderRadius: { xs: "1.1rem", sm: "1.2rem" },
        background: "var(--card-bg)",
        color: "var(--page-text)",
        position: "relative",
        cursor: hoveringDisabled ? "default" : "pointer",
        boxShadow: 5,
        p: 0,
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        minHeight: 340,
        "&:focus-visible": {
          outline: "2px solid var(--nav-link)",
          outlineOffset: "2px",
        },
      }}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (editOpen) return
        if (e.currentTarget !== e.target) return
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault()
          navigate(`/news/${id}`)
        }
      }}
      onClick={handleCardClick}
    >
      {user?.role === "admin" && (
        <>
          <IconButton
            aria-label={t("news:aria.cardActions")}
            aria-controls={menuAnchor ? menuId : undefined}
            aria-haspopup="true"
            aria-expanded={Boolean(menuAnchor) ? "true" : undefined}
            sx={{
              position: "absolute",
              top: 10,
              right: 10,
              zIndex: 2,
              bgcolor: "rgba(255,255,255,0.82)",
              "&:hover": { bgcolor: "#fff" },
            }}
            onClick={(e) => {
              e.stopPropagation()
              setMenuAnchor(e.currentTarget)
            }}
            size="small"
            disabled={loading}
          >
            <MoreVertIcon />
          </IconButton>
          <Menu
            id={menuId}
            anchorEl={menuAnchor}
            open={Boolean(menuAnchor)}
            onClose={(e) => {
              if (e) (e as any).stopPropagation?.()
              setMenuAnchor(null)
            }}
            anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
            transformOrigin={{ vertical: "top", horizontal: "right" }}
            MenuListProps={{ "aria-labelledby": menuId }}
          >
            <MenuItem
              onClick={(e) => {
                e.stopPropagation()
                openEditDialog()
                setMenuAnchor(null)
              }}
            >
              <EditIcon fontSize="small" sx={{ mr: 1 }} />
              {t("common:buttons.edit")}
            </MenuItem>
            <MenuItem
              onClick={(e) => {
                e.stopPropagation()
                setConfirmDeleteOpen(true)
                setMenuAnchor(null)
              }}
            >
              <DeleteIcon fontSize="small" sx={{ mr: 1 }} color="error" />
              <span style={{ color: "#d32f2f" }}>{t("common:buttons.delete")}</span>
            </MenuItem>
          </Menu>
        </>
      )}

      <Box
        sx={{
          width: "100%",
          height: { xs: 160, sm: 180, md: 220, lg: 240 },
          borderTopLeftRadius: { xs: "1.1rem", sm: "1.2rem" },
          borderTopRightRadius: { xs: "1.1rem", sm: "1.2rem" },
          borderBottom: "1px solid #eee",
          background: "linear-gradient(135deg, rgba(13,71,161,0.18), rgba(63,81,181,0.08))",
          position: "relative",
          overflow: "hidden",
          display: "flex",
          alignItems: "stretch",
          "& img": {
            display: "block",
            width: "100%",
            height: "100%",
            objectFit: "cover",
            objectPosition: "center",
          },
          "&::after": {
            content: '""',
            position: "absolute",
            inset: 0,
            background: "linear-gradient(120deg, rgba(255,255,255,0.2), rgba(255,255,255,0.05))",
            opacity: cardImageReady ? 0 : 1,
            transition: "opacity 260ms ease",
            pointerEvents: "none",
          },
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
          style={{
            width: "100%",
            height: "100%",
            display: "block",
            objectFit: "cover",
            objectPosition: "center",
          }}
          onLoad={handleCardImageReady}
          onError={handleCardImageReady}
        />
      </Box>

      <Box
        sx={{
          p: { xs: 2, sm: 3 },
          flex: 1,
          display: "flex",
          flexDirection: "column",
        }}
      >
        <Typography
          fontWeight={700}
          variant="h6"
          mb={1}
          sx={{
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            fontSize: "clamp(1.07rem, 3vw, 1.18rem)",
          }}
        >
          {localizedTitle}
        </Typography>

        <Typography
          mb={2}
          variant="body2"
          color="text.secondary"
          sx={{
            minHeight: { xs: 44, sm: 64 },
            overflow: "hidden",
            display: "-webkit-box",
            WebkitLineClamp: 3,
            WebkitBoxOrient: "vertical",
            fontSize: "clamp(0.99rem, 2vw, 1.06rem)",
          }}
        >
          {sanitizedPreview}
        </Typography>

        <Box flex={1} />

        <Typography color="var(--secondary-text)" fontSize={14} sx={{ mt: "auto" }}>
          {createdAtIso && <time dateTime={createdAtIso}>{createdAtLabel}</time>}
        </Typography>
      </Box>

      {/* Edit dialog */}
      <Dialog
        open={editOpen}
        onClose={closeEditDialog}
        fullScreen={isMobile}
        PaperProps={{
          sx: {
            borderRadius: { xs: 0, sm: 3 },
            width: { xs: "100vw", sm: 420 },
            maxWidth: { xs: "100vw", sm: 450 },
          },
        }}
      >
        <DialogTitle sx={{ fontWeight: 700, fontSize: "1.2rem" }}>
          {t("news:dialogs.edit.title")}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} mt={1} minWidth={isMobile ? "auto" : 340} mb={2}>
            <TextField
              label={t("news:form.title")}
              value={editData.title}
              onChange={(e) => setEditData({ ...editData, title: e.target.value })}
              fullWidth
              sx={{ fontSize: "1rem" }}
            />
            <TextField
              label={t("news:form.text")}
              value={editData.content}
              onChange={(e) => setEditData({ ...editData, content: e.target.value })}
              multiline
              rows={4}
              fullWidth
              sx={{ fontSize: "1rem" }}
            />
            <TextField
              label={t("news:form.title_en", { defaultValue: "Title (English)" })}
              value={editData.title_en}
              onChange={(e) => setEditData({ ...editData, title_en: e.target.value })}
              fullWidth
              sx={{ fontSize: "1rem" }}
            />
            <TextField
              label={t("news:form.content_en", { defaultValue: "News text (English)" })}
              value={editData.content_en}
              onChange={(e) => setEditData({ ...editData, content_en: e.target.value })}
              multiline
              rows={4}
              fullWidth
              sx={{ fontSize: "1rem" }}
            />
            <Box>
              <Button
                component="label"
                variant="contained"
                disabled={imageLoading}
                startIcon={<PhotoCamera />}
                sx={{
                  minWidth: 120,
                  fontWeight: 600,
                  fontSize: "1rem",
                  borderRadius: 2,
                }}
                onClick={(e) => e.stopPropagation()}
              >
                {imageLoading ? t("common:statuses.uploading") : t("news:form.changePhoto")}
                <input
                  type="file"
                  accept="image/*"
                  hidden
                  ref={imageInputRef}
                  onChange={handleImageChange}
                  onClick={(e) => e.stopPropagation()}
                />
              </Button>
              {editImageUrl && (
                <Box mt={1}>
                  <SmartImage
                    srcRaw={editImageUrl}
                    alt={t("news:alt.preview")}
                    style={{
                      width: 140,
                      maxHeight: 90,
                      objectFit: "cover",
                      borderRadius: 8,
                      border: "1px solid #eee",
                      display: "block",
                    }}
                  />
                </Box>
              )}
            </Box>

            <Stack direction="row" gap={2} mt={2}>
              <Button
                variant="contained"
                onClick={handleEdit}
                disabled={loading || imageLoading}
                sx={{ fontWeight: 700, borderRadius: 2.2, px: 3, fontSize: "1.02rem" }}
              >
                {t("common:buttons.save")}
              </Button>
              <Button
                variant="outlined"
                color="secondary"
                onClick={closeEditDialog}
                sx={{ borderRadius: 2.2, px: 2.5, fontSize: "1.02rem" }}
              >
                {t("common:buttons.cancel")}
              </Button>
            </Stack>
          </Stack>
        </DialogContent>
      </Dialog>

      {/* Delete confirm */}
      <Dialog open={confirmDeleteOpen} onClose={() => setConfirmDeleteOpen(false)}>
        <DialogTitle>{t("news:dialogs.delete.title")}</DialogTitle>
        <DialogContent>
          <Typography>{t("news:dialogs.delete.description")}</Typography>
        </DialogContent>
        <DialogActions>
          <Button
            variant="outlined"
            color="secondary"
            onClick={() => setConfirmDeleteOpen(false)}
            disabled={loading}
          >
            {t("common:buttons.cancel")}
          </Button>
          <Button variant="contained" color="error" onClick={handleDelete} disabled={loading}>
            <DeleteIcon sx={{ mr: 1 }} /> {t("common:buttons.delete")}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
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
