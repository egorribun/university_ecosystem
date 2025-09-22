import { FC, useState, useEffect, useRef, useCallback } from "react"
import {
  Box, Typography, IconButton, Menu, MenuItem,
  Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, Stack, Button, useMediaQuery
} from "@mui/material"
import MoreVertIcon from "@mui/icons-material/MoreVert"
import EditIcon from "@mui/icons-material/Edit"
import DeleteIcon from "@mui/icons-material/Delete"
import PhotoCamera from "@mui/icons-material/PhotoCamera"
import { useAuth } from "../contexts/AuthContext"
import api from "../api/axios"
import { useNavigate } from "react-router-dom"
import dayjs from "dayjs"
import utc from "dayjs/plugin/utc"
import timezone from "dayjs/plugin/timezone"
import { resolveMediaUrl } from "@/utils/media"

dayjs.extend(utc)
dayjs.extend(timezone)

type NewsCardProps = {
  id: number
  title: string
  content: string
  created_at: string
  image_url?: string
  onChange?: () => void
}

const BACKEND_ORIGIN = import.meta.env.VITE_BACKEND_ORIGIN || ""

const getMoscowDate = (dateStr: string) => {
  let parsed = dayjs(dateStr)
  if (!/([Zz]|[+\-]\d\d:?\d\d)$/.test(dateStr)) {
    parsed = dayjs.utc(dateStr)
  }
  return parsed.tz("Europe/Moscow").format("DD.MM.YYYY HH:mm")
}

const NewsCard: FC<NewsCardProps> = ({
  id,
  title,
  content,
  created_at,
  image_url,
  onChange
}) => {
  const { user } = useAuth()
  const navigate = useNavigate()

  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null)
  const [editOpen, setEditOpen] = useState(false)
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false)

  const [editData, setEditData] = useState({ title, content, image_url: image_url || "" })
  const [loading, setLoading] = useState(false)

  const [newImage, setNewImage] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [imageLoading, setImageLoading] = useState(false)
  const imageInputRef = useRef<HTMLInputElement>(null)

  const isMobile = useMediaQuery("(max-width:600px)")
  const menuId = `news-card-menu-${id}`

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
    setEditData({ title, content, image_url: image_url || "" })
    setEditOpen(true)
    setNewImage(null)
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl)
      setPreviewUrl(null)
    }
    if (imageInputRef.current) imageInputRef.current.value = ""
  }, [title, content, image_url, previewUrl])

  const closeEditDialog = useCallback(() => {
    setEditOpen(false)
    setNewImage(null)
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl)
      setPreviewUrl(null)
    }
    if (imageInputRef.current) imageInputRef.current.value = ""
  }, [previewUrl])

  const getCardImageUrl = () => resolveMediaUrl(image_url, BACKEND_ORIGIN)
  const getEditImageUrl = () => previewUrl || resolveMediaUrl(editData.image_url, BACKEND_ORIGIN)

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) setNewImage(file)
  }

  const handleEdit = async () => {
    setLoading(true)
    try {
      let imgUrl = editData.image_url
      if (newImage) {
        setImageLoading(true)
        const data = new FormData()
        data.append("file", newImage)
        // единый эндпоинт загрузки
        const res = await api.post(`/news/upload_image`, data, {
          headers: { "Content-Type": "multipart/form-data" }
        })
        imgUrl = res.data.url
        setImageLoading(false)
      }
      await api.patch(`/news/${id}`, { ...editData, image_url: imgUrl })
      setEditData(prev => ({ ...prev, image_url: imgUrl }))
      closeEditDialog()
      onChange && onChange()
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async () => {
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
  }

  const handleCardClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
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
    ) return
    navigate(`/news/${id}`)
  }, [editOpen, id, navigate])

  const hoveringDisabled = editOpen || Boolean(menuAnchor)

  return (
    <Box
      className="news-card"
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
        transition: "transform 0.25s ease, box-shadow 0.25s ease",
        willChange: "transform",
        "&:hover": {
          transform: hoveringDisabled ? "none" : "scale(1.03)",
          boxShadow: hoveringDisabled ? 5 : "0 12px 28px rgba(0,0,0,0.18)"
        },
        "&:active": {
          transform: hoveringDisabled ? "none" : "scale(0.997)"
        },
        "&:focus-visible": {
          outline: "2px solid var(--nav-link)",
          outlineOffset: "2px"
        },
        "@media (prefers-reduced-motion: reduce)": {
          transition: "box-shadow 0.25s ease"
        }
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
            aria-label="Действия с новостью"
            aria-controls={menuAnchor ? menuId : undefined}
            aria-haspopup="true"
            aria-expanded={Boolean(menuAnchor) ? "true" : undefined}
            sx={{
              position: "absolute",
              top: 10,
              right: 10,
              zIndex: 2,
              bgcolor: "rgba(255,255,255,0.82)",
              "&:hover": { bgcolor: "#fff" }
            }}
            onClick={e => {
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
            onClose={e => { if (e) (e as any).stopPropagation?.(); setMenuAnchor(null) }}
            anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
            transformOrigin={{ vertical: "top", horizontal: "right" }}
            MenuListProps={{ "aria-labelledby": menuId }}
          >
            <MenuItem onClick={e => { e.stopPropagation(); openEditDialog(); setMenuAnchor(null) }}>
              <EditIcon fontSize="small" sx={{ mr: 1 }} />
              Редактировать
            </MenuItem>
            <MenuItem onClick={e => { e.stopPropagation(); setConfirmDeleteOpen(true); setMenuAnchor(null) }}>
              <DeleteIcon fontSize="small" sx={{ mr: 1 }} color="error" />
              <span style={{ color: "#d32f2f" }}>Удалить</span>
            </MenuItem>
          </Menu>
        </>
      )}

      {getCardImageUrl() && (
        <Box
          component="img"
          src={getCardImageUrl() || ""}
          alt="Новость"
          sx={{
            width: "100%",
            height: { xs: 160, sm: 180, md: 220, lg: 240 },
            objectFit: "cover",
            borderTopLeftRadius: { xs: "1.1rem", sm: "1.2rem" },
            borderTopRightRadius: { xs: "1.1rem", sm: "1.2rem" },
            borderBottom: "1px solid #eee",
            background: "#f3f3f3",
            display: "block"
          }}
          onError={e => { (e.target as HTMLImageElement).style.display = "none" }}
        />
      )}

      <Box sx={{
        p: { xs: 2, sm: 3 },
        flex: 1,
        display: "flex",
        flexDirection: "column"
      }}>
        <Typography fontWeight={700} variant="h6" mb={1} sx={{
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          fontSize: "clamp(1.07rem, 3vw, 1.18rem)"
        }}>
          {title}
        </Typography>

        <Typography mb={2} variant="body2" color="text.secondary" sx={{
          minHeight: { xs: 44, sm: 64 },
          overflow: "hidden",
          display: "-webkit-box",
          WebkitLineClamp: 3,
          WebkitBoxOrient: "vertical",
          fontSize: "clamp(0.99rem, 2vw, 1.06rem)"
        }}>
          {content}
        </Typography>

        <Box flex={1} />

        <Typography color="var(--secondary-text)" fontSize={14} sx={{ mt: "auto" }}>
          {created_at && (
            <time dateTime={dayjs(created_at).toISOString()}>
              {getMoscowDate(created_at)}
            </time>
          )}
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
            maxWidth: { xs: "100vw", sm: 450 }
          }
        }}
      >
        <DialogTitle sx={{ fontWeight: 700, fontSize: "1.2rem" }}>
          Редактировать новость
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} mt={1} minWidth={isMobile ? "auto" : 340} mb={2}>
            <TextField
              label="Заголовок"
              value={editData.title}
              onChange={e => setEditData({ ...editData, title: e.target.value })}
              fullWidth
              sx={{ fontSize: "1rem" }}
            />
            <TextField
              label="Текст"
              value={editData.content}
              onChange={e => setEditData({ ...editData, content: e.target.value })}
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
                  borderRadius: 2
                }}
                onClick={e => e.stopPropagation()}
              >
                {imageLoading ? "Загрузка..." : "Изменить фото"}
                <input
                  type="file"
                  accept="image/*"
                  hidden
                  ref={imageInputRef}
                  onChange={handleImageChange}
                  onClick={e => e.stopPropagation()}
                />
              </Button>
              {getEditImageUrl() && (
                <Box mt={1}>
                  <img
                    src={getEditImageUrl()!}
                    alt="preview"
                    style={{
                      width: 140,
                      maxHeight: 90,
                      objectFit: "cover",
                      borderRadius: 8,
                      border: "1px solid #eee"
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
                Сохранить
              </Button>
              <Button
                variant="outlined"
                color="secondary"
                onClick={closeEditDialog}
                sx={{ borderRadius: 2.2, px: 2.5, fontSize: "1.02rem" }}
              >
                Отмена
              </Button>
            </Stack>
          </Stack>
        </DialogContent>
      </Dialog>

      {/* Delete confirm */}
      <Dialog open={confirmDeleteOpen} onClose={() => setConfirmDeleteOpen(false)}>
        <DialogTitle>Удалить новость?</DialogTitle>
        <DialogContent>
          <Typography>Действие необратимо. Подтвердите удаление.</Typography>
        </DialogContent>
        <DialogActions>
          <Button
            variant="outlined"
            color="secondary"
            onClick={() => setConfirmDeleteOpen(false)}
            disabled={loading}
          >
            Отмена
          </Button>
          <Button
            variant="contained"
            color="error"
            onClick={handleDelete}
            disabled={loading}
          >
            <DeleteIcon sx={{ mr: 1 }} /> Удалить
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

export default NewsCard