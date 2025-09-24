import { useParams, useNavigate } from 'react-router-dom'
import { useEffect, useState, useRef } from 'react'
import api from '../api/axios'
import {
  Box, Typography, Paper, Stack, IconButton, TextField,
  Dialog, DialogTitle, DialogContent, DialogActions, Divider, Button, useMediaQuery, Snackbar, Skeleton
} from '@mui/material'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import DeleteIcon from '@mui/icons-material/Delete'
import EditIcon from '@mui/icons-material/Edit'
import SaveIcon from '@mui/icons-material/Save'
import CloseIcon from '@mui/icons-material/Close'
import PhotoCamera from '@mui/icons-material/PhotoCamera'
import { useAuth } from '../contexts/AuthContext'
import Layout from "../components/Layout"
import { resolveMediaUrl } from '@/utils/media'

import dayjs from "dayjs"
import utc from "dayjs/plugin/utc"
import timezone from "dayjs/plugin/timezone"
dayjs.extend(utc)
dayjs.extend(timezone)

const BACKEND_ORIGIN = import.meta.env.VITE_BACKEND_ORIGIN || ""

const getMoscowDate = (dateStr: string) => {
  let parsed = dayjs(dateStr)
  if (!/([Zz]|[+\-]\d\d:?\d\d)$/.test(dateStr)) parsed = dayjs.utc(dateStr)
  return parsed.tz("Europe/Moscow").format("DD.MM.YYYY HH:mm")
}

const NewsDetail = () => {
  const { id } = useParams()
  const navigate = useNavigate()
  const { user } = useAuth()
  const isMobile = useMediaQuery('(max-width:600px)')

  const [news, setNews] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  const [editOpen, setEditOpen] = useState(false)
  const [editData, setEditData] = useState({ title: '', content: '', image_url: '' })
  const [saving, setSaving] = useState(false)

  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const [newImage, setNewImage] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const imageInputRef = useRef<HTMLInputElement>(null)

  const [snack, setSnack] = useState('')

  useEffect(() => {
    loadNews()
    return () => {
      resetPreview()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  const loadNews = () => {
    setLoading(true)
    api.get(`/news/${id}`)
      .then(res => setNews(res.data))
      .catch(err => {
        console.error(err)
        setNews(null)
        setSnack('Не удалось загрузить новость')
      })
      .finally(() => setLoading(false))
  }

  const resetPreview = () => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl)
      setPreviewUrl(null)
    }
    if (imageInputRef.current) imageInputRef.current.value = ''
    setNewImage(null)
  }

  const openEdit = () => {
    if (!news) return
    setEditData({
      title: news.title || '',
      content: news.content || '',
      image_url: news.image_url || ""
    })
    resetPreview()
    setEditOpen(true)
  }

  const closeEdit = () => {
    resetPreview()
    setEditOpen(false)
  }

  const handleSave = async () => {
    if (!news) return
    setSaving(true)
    try {
      let imgUrl = editData.image_url || ''
      if (newImage) {
        const data = new FormData()
        data.append('file', newImage)
        const res = await api.post('/news/upload_image', data, {
          headers: { 'Content-Type': 'multipart/form-data' }
        })
        imgUrl = res.data.url
      }
      await api.patch(`/news/${news.id}`, { ...editData, image_url: imgUrl })
      closeEdit()
      setSnack('Новость обновлена')
      loadNews()
    } catch (err) {
      console.error(err)
      setSnack('Ошибка сохранения')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!news) return
    setDeleting(true)
    try {
      await api.delete(`/news/${news.id}`)
      setSnack('Новость удалена')
      // аккуратный выход: если истории нет — уходим на список
      if (window.history.length > 1) navigate(-1)
      else navigate('/news')
    } catch (err) {
      console.error(err)
      setSnack('Ошибка удаления')
    } finally {
      setDeleting(false)
      setConfirmDeleteOpen(false)
    }
  }

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      if (previewUrl) URL.revokeObjectURL(previewUrl)
      setNewImage(file)
      setPreviewUrl(URL.createObjectURL(file))
    }
  }

  const getImageUrl = () => {
    if (previewUrl) return previewUrl
    const path = editOpen ? editData.image_url : news?.image_url
    if (!path) return ''
    return resolveMediaUrl(path, BACKEND_ORIGIN)
  }

  const handleBack = () => {
    if (window.history.length > 1) navigate(-1)
    else navigate('/news')
  }

  if (loading) {
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
            boxSizing: "border-box"
          }}
        >
          <Skeleton variant="rounded" width={140} height={44} sx={{ mb: 3, maxWidth: 220 }} />
          <Stack spacing={3} sx={{ flex: 1 }}>
            <Skeleton variant="text" width="72%" height={52} />
            <Skeleton variant="rounded" height={240} sx={{ borderRadius: 3 }} />
            <Stack spacing={1.4}>
              {Array.from({ length: 6 }).map((_, idx) => (
                <Skeleton key={idx} variant="text" height={28} width={idx % 2 === 0 ? "100%" : "86%"} />
              ))}
            </Stack>
            <Skeleton variant="rounded" height={56} sx={{ borderRadius: 2, width: { xs: "100%", sm: "60%", md: "48%" } }} />
          </Stack>
        </Paper>
      </Layout>
    )
  }

  if (!news) {
    return (
      <Layout>
        <Box minHeight="80vh" display="flex" alignItems="center" justifyContent="center">
          <Typography>Новость не найдена</Typography>
        </Box>
      </Layout>
    )
  }

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
          boxSizing: "border-box"
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
              boxShadow: "0 6px 28px #1d5fff40, 0 2.5px 10px #0002"
            },
            "&:active": { transform: "scale(0.98)" }
          }}
        >
          Назад
        </Button>

        <Stack spacing={2} width="100%" alignSelf="flex-start">
          <Box display="flex" alignItems="center" flexWrap="wrap">
            <Typography
              variant="h3"
              fontWeight={900}
              sx={{ mr: 2, fontSize: "clamp(1.28rem,4vw,2.1rem)" }}
            >
              {news.title}
            </Typography>

            {user?.role === "admin" && (
              <>
                <IconButton
                  color="primary"
                  onClick={openEdit}
                  sx={{ mr: 1 }}
                  aria-label="Редактировать новость"
                  disabled={saving || deleting}
                >
                  <EditIcon />
                </IconButton>
                <IconButton
                  color="error"
                  onClick={() => setConfirmDeleteOpen(true)}
                  aria-label="Удалить новость"
                  disabled={deleting || saving}
                >
                  <DeleteIcon />
                </IconButton>
              </>
            )}
          </Box>

          <Typography color="text.secondary" fontSize="clamp(0.92rem,1.5vw,1.12rem)">
            Опубликовано: {news.created_at && (
              <time dateTime={dayjs(news.created_at).toISOString()}>
                {getMoscowDate(news.created_at)}
              </time>
            )}
          </Typography>

          {getImageUrl() && (
            <Box
              component="img"
              src={getImageUrl()}
              alt={news.title || "Новость"}
              loading="lazy"
              decoding="async"
              sx={{
                width: "100%",
                maxWidth: { xs: "100%", md: 800, lg: 1000 },
                maxHeight: { xs: 220, sm: 340, md: 420, lg: 500 },
                objectFit: "cover",
                borderRadius: 4,
                border: "1px solid #eee",
                mb: 2,
                background: "#f7f8fa"
              }}
              onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
            />
          )}

          <Divider sx={{ my: 2 }} />

          <Typography
            variant="body1"
            fontSize="clamp(1.07rem,2.3vw,1.24rem)"
            sx={{ whiteSpace: "pre-line" }}
          >
            {news.content}
          </Typography>
        </Stack>

        {/* Редактирование */}
        <Dialog open={editOpen} onClose={closeEdit} fullScreen={isMobile}>
          <DialogTitle>Редактировать новость</DialogTitle>
          <DialogContent>
            <Stack spacing={2} mt={1}>
              <TextField
                label="Заголовок"
                value={editData.title}
                onChange={e => setEditData({ ...editData, title: e.target.value })}
                fullWidth
                disabled={saving}
              />
              <TextField
                label="Текст"
                value={editData.content}
                onChange={e => setEditData({ ...editData, content: e.target.value })}
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
                  {newImage ? "Изменить фото" : "Загрузить фото"}
                  <input
                    type="file"
                    accept="image/*"
                    hidden
                    ref={imageInputRef}
                    onChange={handleImageChange}
                  />
                </Button>

                {getImageUrl() && (
                  <Box>
                    <img
                      src={getImageUrl()}
                      alt="preview"
                      style={{
                        width: 120,
                        maxHeight: 70,
                        objectFit: "cover",
                        borderRadius: 8,
                        border: "1px solid #eee"
                      }}
                    />
                  </Box>
                )}
              </Box>
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button variant="contained" onClick={handleSave} disabled={saving}>
              <SaveIcon sx={{ mr: 1 }} /> Сохранить
            </Button>
            <Button variant="outlined" color="secondary" onClick={closeEdit} disabled={saving}>
              <CloseIcon sx={{ mr: 1 }} /> Отмена
            </Button>
          </DialogActions>
        </Dialog>

        {/* Подтверждение удаления */}
        <Dialog
          open={confirmDeleteOpen}
          onClose={() => setConfirmDeleteOpen(false)}
          fullScreen={isMobile}
        >
          <DialogTitle>Удалить новость?</DialogTitle>
          <DialogContent>
            <Typography>Действие необратимо. Подтвердите удаление.</Typography>
          </DialogContent>
          <DialogActions>
            <Button
              variant="outlined"
              color="secondary"
              onClick={() => setConfirmDeleteOpen(false)}
              disabled={deleting}
            >
              Отмена
            </Button>
            <Button
              variant="contained"
              color="error"
              onClick={handleDelete}
              disabled={deleting}
            >
              <DeleteIcon sx={{ mr: 1 }} /> Удалить
            </Button>
          </DialogActions>
        </Dialog>

        <Snackbar
          open={!!snack}
          autoHideDuration={2400}
          onClose={() => setSnack('')}
          message={snack}
        />
      </Paper>
    </Layout>
  )
}

export default NewsDetail