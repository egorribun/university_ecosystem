import type React from "react"
import { useEffect, useMemo, useRef, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Box,
  Typography,
  CircularProgress,
  Paper,
  Stack,
  Button,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Divider,
  Snackbar,
  useMediaQuery,
} from "@mui/material"
import ArrowBackIcon from "@mui/icons-material/ArrowBack"
import EditIcon from "@mui/icons-material/Edit"
import DeleteIcon from "@mui/icons-material/Delete"
import SaveIcon from "@mui/icons-material/Save"
import CloseIcon from "@mui/icons-material/Close"
import PhotoCamera from "@mui/icons-material/PhotoCamera"
import dayjs from "dayjs"
import utc from "dayjs/plugin/utc"
import timezone from "dayjs/plugin/timezone"
import api from "@/api/client"
import Layout from "@/components/Layout"
import SmartImage from "@/components/SmartImage"
import { useAuth } from "@/contexts/AuthContext"
import { useTranslation } from "react-i18next"

dayjs.extend(utc)
dayjs.extend(timezone)

type NewsItem = {
  id: number
  title: string
  content: string
  image_url?: string | null
  created_at?: string
}

async function fetchNews(id: string) {
  const { data } = await api.get<NewsItem>(`/news/${id}`)
  return data
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
  const queryClient = useQueryClient()
  const isMobile = useMediaQuery("(max-width:600px)")

  const [editOpen, setEditOpen] = useState(false)
  const [editData, setEditData] = useState({ title: "", content: "", image_url: "" })
  const [saving, setSaving] = useState(false)
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [newImage, setNewImage] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [snack, setSnack] = useState("")
  const imageInputRef = useRef<HTMLInputElement>(null)
  const [heroPos, setHeroPos] = useState<'50% 18%' | '50% 38%' | '50% 50%' | string>('50% 38%')

  const handleHeroLoad: React.ReactEventHandler<HTMLImageElement> = (e) => {
    const img = e.currentTarget
    const w = img.naturalWidth || 0
    const h = img.naturalHeight || 0
    if (!w || !h) return
    const r = w / h
    if (r < 0.9) setHeroPos('50% 18%')
    else if (r > 2) setHeroPos('50% 50%')
    else setHeroPos('50% 38%')
  }

  const query = useQuery({
    queryKey: ["news", id],
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

  const openEdit = () => {
    if (!query.data) return
    setEditData({
      title: query.data.title || "",
      content: query.data.content || "",
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
        const data = new FormData()
        data.append("file", newImage)
        const res = await api.post<{ url: string }>("/news/upload_image", data, {
          headers: { "Content-Type": "multipart/form-data" },
        })
        imageUrl = res.data.url
      }
      const payload = { ...editData, image_url: imageUrl }
      const { data } = await api.patch<NewsItem>(`/news/${query.data.id}`, payload)
      queryClient.setQueryData(["news", id], data)
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
      await api.delete(`/news/${query.data.id}`)
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
    setHeroPos('50% 38%')
  }, [imageUrl])

  const content = query.data?.content ?? ""
  const createdAt = query.data?.created_at
  const createdAtIso = useMemo(
    () => (createdAt ? dayjs(createdAt).toISOString() : ""),
    [createdAt],
  )
  const createdAtLabel = useMemo(
    () => (createdAt ? getMoscowDate(createdAt) : ""),
    [createdAt],
  )

  if (query.isLoading)
    return (
      <Layout>
        <Box sx={{ minHeight: "60vh", display: "grid", placeItems: "center" }}>
          <CircularProgress />
        </Box>
      </Layout>
    )

  if (query.isError || !query.data)
    return (
      <Layout>
        <Box sx={{ p: 2 }}>
          <Typography color="error">{t("news:states.loadError")}</Typography>
        </Box>
      </Layout>
    )

  return (
    <Layout>
      <Paper
        elevation={0}
        sx={{
          width: "100vw",
          minHeight: "calc(100vh - 56px)",
          bgcolor: "background.paper",
          borderRadius: 0,
          boxShadow: "none",
          display: "flex",
          flexDirection: "column",
          pl: { xs: 2, sm: 4, md: 5, lg: 8 },
          pr: { xs: 4, sm: 6, md: 7, lg: 10 },
          py: { xs: 2, sm: 2, md: 2, lg: 2 },
          boxSizing: "border-box",
        }}
      >
        <Button
          onClick={handleBack}
          startIcon={<ArrowBackIcon />}
          sx={{
            mb: 3,
            alignSelf: "flex-start",
            fontWeight: 700,
            borderRadius: 2.5,
            background: "linear-gradient(100deg, #1d5fff 20%, #65b2ff 100%)",
            color: "#fff",
            fontSize: "clamp(0.98rem, 2.1vw, 1.17rem)",
            letterSpacing: "0.02em",
            px: { xs: 1.6, sm: 2.3, md: 2.9, lg: 3.5 },
            py: { xs: 0.9, sm: 1.12, md: 1.2, lg: 1.28 },
            width: { xs: "100%", sm: "auto" },
            minWidth: { xs: 0, sm: 0 },
            boxShadow: "0 2px 18px #1976d238, 0 1.5px 8px #0001",
            transition: "transform 0.16s, box-shadow 0.16s, background 0.19s, color 0.16s",
            "&:hover": {
              background: "linear-gradient(100deg, #1976d2 20%, #449aff 100%)",
              color: "#eaf6ff",
              transform: "scale(1.06)",
              boxShadow: "0 6px 28px #1d5fff40, 0 2.5px 10px #0002",
            },
            "&:active": { transform: "scale(0.98)" },
          }}
        >
          {t("common:buttons.back")}
        </Button>

        <Stack spacing={2} width="100%" alignSelf="flex-start">
          <Box display="flex" alignItems="center" flexWrap="wrap">
            <Typography
              variant="h3"
              fontWeight={900}
              sx={{ mr: 2, fontSize: "clamp(1.28rem,4vw,2.1rem)" }}
            >
              {query.data.title}
            </Typography>

            {user?.role === "admin" && (
              <>
                <IconButton
                  color="primary"
                  onClick={openEdit}
                  sx={{ mr: 1 }}
                  aria-label={t("news:aria.editNews")}
                  disabled={saving || deleting}
                >
                  <EditIcon />
                </IconButton>
                <IconButton
                  color="error"
                  onClick={() => setConfirmDeleteOpen(true)}
                  aria-label={t("news:aria.deleteNews")}
                  disabled={deleting || saving}
                >
                  <DeleteIcon />
                </IconButton>
              </>
            )}
          </Box>

            {createdAt && (
              <Typography color="text.secondary" fontSize="clamp(0.92rem,1.5vw,1.12rem)">
                {t("news:meta.published")} {" "}
                <time dateTime={createdAtIso}>{createdAtLabel}</time>
              </Typography>
            )}

          <Box
            sx={{
              width: "100%",
              maxWidth: { xs: "100%", md: 800, lg: 1000 },
              aspectRatio: { xs: "16 / 9", md: "21 / 9" },
              position: "relative",
              borderRadius: 4,
              border: "1px solid #eee",
              overflow: "hidden",
              bgcolor: "rgba(0,0,0,0.04)",
            }}
          >
              <SmartImage
                srcRaw={imageUrl}
                alt={
                  query.data.title
                    ? t("news:alt.hero", { title: query.data.title })
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
          </Box>

          <Divider sx={{ my: 2 }} />

          <Typography
            variant="body1"
            fontSize="clamp(1.07rem,2.3vw,1.24rem)"
            sx={{ whiteSpace: "pre-line" }}
          >
            {content}
          </Typography>
        </Stack>

          <Dialog open={editOpen} onClose={closeEdit} fullScreen={isMobile}>
            <DialogTitle>{t("news:dialogs.edit.title")}</DialogTitle>
            <DialogContent>
              <Stack spacing={2} mt={1}>
                <TextField
                  label={t("news:form.title")}
                  value={editData.title}
                  onChange={(e) => setEditData({ ...editData, title: e.target.value })}
                  fullWidth
                  disabled={saving}
                />
                <TextField
                  label={t("news:form.text")}
                  value={editData.content}
                  onChange={(e) => setEditData({ ...editData, content: e.target.value })}
                  multiline
                  rows={4}
                  fullWidth
                disabled={saving}
              />
              <Box display="flex" gap={2} alignItems="center" mt={1}>
                  <Button
                    component="label"
                    variant="outlined"
                    startIcon={<PhotoCamera />}
                    sx={{ minWidth: 140 }}
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

                {imageUrl && (
                    <Box sx={{ width: 120, maxHeight: 70, borderRadius: 2, overflow: "hidden" }}>
                      <SmartImage
                        srcRaw={imageUrl}
                        alt={t("news:alt.preview")}
                        style={{ width: "100%", height: "100%", objectFit: "cover" }}
                      />
                    </Box>
                  )}
                </Box>
              </Stack>
            </DialogContent>
            <DialogActions>
              <Button variant="contained" onClick={handleSave} disabled={saving}>
                <SaveIcon sx={{ mr: 1 }} /> {t("common:buttons.save")}
              </Button>
              <Button variant="outlined" color="secondary" onClick={closeEdit} disabled={saving}>
                <CloseIcon sx={{ mr: 1 }} /> {t("common:buttons.cancel")}
              </Button>
            </DialogActions>
          </Dialog>

          <Dialog
            open={confirmDeleteOpen}
            onClose={() => setConfirmDeleteOpen(false)}
            fullScreen={isMobile}
          >
            <DialogTitle>{t("news:dialogs.delete.title")}</DialogTitle>
            <DialogContent>
              <Typography>{t("news:dialogs.delete.description")}</Typography>
            </DialogContent>
            <DialogActions>
              <Button
                variant="outlined"
                color="secondary"
                onClick={() => setConfirmDeleteOpen(false)}
                disabled={deleting}
              >
                {t("common:buttons.cancel")}
              </Button>
              <Button variant="contained" color="error" onClick={handleDelete} disabled={deleting}>
                <DeleteIcon sx={{ mr: 1 }} /> {t("common:buttons.delete")}
              </Button>
            </DialogActions>
          </Dialog>

        <Snackbar
          open={!!snack}
          autoHideDuration={2400}
          onClose={() => setSnack("")}
          message={snack}
        />
      </Paper>
    </Layout>
  )
}
