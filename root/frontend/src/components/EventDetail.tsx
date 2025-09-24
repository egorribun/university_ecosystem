import { useParams, useNavigate } from 'react-router-dom'
import { useEffect, useState, useRef, useCallback } from 'react'
import api from '../api/axios'
import {
  Box, Typography, Paper, Stack, Chip, Button, Divider,
  IconButton, TextField, useMediaQuery, Snackbar, Skeleton
} from '@mui/material'
import PeopleAltIcon from '@mui/icons-material/PeopleAlt'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import DeleteIcon from '@mui/icons-material/Delete'
import EditIcon from '@mui/icons-material/Edit'
import SaveIcon from '@mui/icons-material/Save'
import CloseIcon from '@mui/icons-material/Close'
import { useAuth } from '../contexts/AuthContext'
import Layout from '../components/Layout'
import { resolveMediaUrl } from '@/utils/media'
import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc'
import timezone from 'dayjs/plugin/timezone'

dayjs.extend(utc)
dayjs.extend(timezone)

const BACKEND_ORIGIN = import.meta.env.VITE_BACKEND_ORIGIN || ''

const formatLocalDateTime = (s?: string) => {
  if (!s) return '—'
  const norm = s.replace(' ', 'T')
  const withSec = norm.length === 16 ? norm + ':00' : norm
  const d = dayjs(withSec)
  return d.isValid() ? d.format('DD.MM.YYYY HH:mm') : '—'
}
const formatDateSafe = (v?: string) => formatLocalDateTime(v)

const EventDetail = () => {
  const { id } = useParams()
  const navigate = useNavigate()
  const { user } = useAuth()
  const isMobile = useMediaQuery('(max-width: 900px)')

  const [event, setEvent] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  const [fileLoading, setFileLoading] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const [editingAbout, setEditingAbout] = useState(false)
  const [aboutDraft, setAboutDraft] = useState('')
  const [savingAbout, setSavingAbout] = useState(false)

  const [snack, setSnack] = useState('')
  const aboutSectionRef = useRef<HTMLHeadingElement | null>(null)

  const loadEvent = useCallback(() => {
    const controller = new AbortController()
    setLoading(true)
    api.get(`/events/${id}`, { signal: controller.signal as any })
      .then(res => setEvent(res.data))
      .catch((err) => {
        if (err?.name !== 'CanceledError' && err?.code !== 'ERR_CANCELED') {
          setSnack('Ошибка загрузки')
        }
      })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [id])

  useEffect(() => {
    const clean = loadEvent()
    return () => clean && clean()
  }, [loadEvent])

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSelectedFile(e.target.files?.[0] || null)
  }

  const handleFileUpload = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedFile) return
    setFileLoading(true)
    try {
      const data = new FormData()
      data.append('file', selectedFile)
      await api.post(`/events/${id}/upload_file`, data, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      setSnack('Файл добавлен')
      setSelectedFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
      loadEvent()
    } catch {
      setSnack('Ошибка добавления файла')
    } finally {
      setFileLoading(false)
    }
  }

  const handleDeleteFile = async (fileId: number) => {
    try {
      await api.delete(`/events/file/${fileId}`)
      setSnack('Файл удалён')
      loadEvent()
    } catch {
      setSnack('Ошибка удаления файла')
    }
  }

  const handleEditAbout = () => {
    setAboutDraft(event.about || '')
    setEditingAbout(true)
  }

  const handleSaveAbout = async () => {
    setSavingAbout(true)
    try {
      await api.patch(`/events/${event.id}`, { about: aboutDraft.trim() })
      setEditingAbout(false)
      setSnack('Описание обновлено')
      loadEvent()
      setTimeout(() => aboutSectionRef.current?.focus?.(), 0)
    } catch {
      setSnack('Ошибка сохранения описания')
    } finally {
      setSavingAbout(false)
    }
  }

  const handleCancelAbout = () => {
    setEditingAbout(false)
    setAboutDraft('')
  }

  const handleBack = () => {
    const canGoBack = (window.history?.state && typeof window.history.state.idx === 'number' && window.history.state.idx > 0)
    if (canGoBack) navigate(-1)
    else navigate('/events')
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
            pl: { xs: 2, sm: 4, md: 5, lg: 8 },
            pr: { xs: 4, sm: 6, md: 7, lg: 10 },
            py: { xs: 2, sm: 2, md: 2, lg: 2 },
            boxSizing: "border-box"
          }}
        >
          <Skeleton variant="rounded" width={140} height={44} sx={{ mb: 3, maxWidth: 220 }} />
          <Stack spacing={3} sx={{ flex: 1 }}>
            <Skeleton variant="text" width="64%" height={52} />
            <Skeleton variant="rounded" height={220} sx={{ borderRadius: 3 }} />
            <Stack spacing={1.4}>
              {Array.from({ length: 5 }).map((_, idx) => (
                <Skeleton key={idx} variant="text" height={26} width={idx % 2 === 0 ? "100%" : "82%"} />
              ))}
            </Stack>
            <Skeleton variant="rounded" height={48} sx={{ borderRadius: 2, width: { xs: "100%", sm: "70%", md: "50%" } }} />
          </Stack>
        </Paper>
      </Layout>
    )
  }

  if (!event) {
    return (
      <Layout>
        <Box minHeight="80vh" display="flex" alignItems="center" justifyContent="center">
          <Typography>Мероприятие не найдено</Typography>
        </Box>
      </Layout>
    )
  }

  const imageUrl = resolveMediaUrl(event.image_url, BACKEND_ORIGIN)

  const BackButton = (
    <Button
      onClick={handleBack}
      startIcon={<ArrowBackIcon />}
      sx={{
        mb: 3,
        alignSelf: 'flex-start',
        fontWeight: 700,
        borderRadius: 2.5,
        background: 'linear-gradient(100deg, #1d5fff 20%, #65b2ff 100%)',
        color: '#fff',
        fontSize: 'clamp(0.98rem, 2.1vw, 1.17rem)',
        letterSpacing: '0.02em',
        px: { xs: 1.6, sm: 2.3, md: 2.9, lg: 3.5 },
        py: { xs: 0.9, sm: 1.12, md: 1.2, lg: 1.28 },
        width: { xs: '100%', sm: 'auto' },
        minWidth: { xs: 0, sm: 0 },
        boxShadow: '0 2px 18px #1976d238, 0 1.5px 8px #0001',
        transition: 'transform 0.16s, box-shadow 0.16s, background 0.19s, color 0.16s',
        '&:hover': {
          background: 'linear-gradient(100deg, #1976d2 20%, #449aff 100%)',
          color: '#eaf6ff',
          transform: 'scale(1.06)',
          boxShadow: '0 6px 28px #1d5fff40, 0 2.5px 10px #0002'
        },
        '&:active': { transform: 'scale(0.98)' },
        position: { xs: 'static', md: 'sticky' },
        top: { md: 12 },
        zIndex: 99
      }}
    >
      Назад
    </Button>
  )

  if (isMobile) {
    return (
      <Layout>
        <Paper
          elevation={0}
          sx={{
            width: '100vw',
            minHeight: 'calc(100vh - 56px)',
            bgcolor: 'background.paper',
            borderRadius: 0,
            boxShadow: 'none',
            pl: { xs: 2, sm: 4, md: 5, lg: 8 },
            pr: { xs: 4, sm: 6, md: 7, lg: 10 },
            py: { xs: 2, md: 2 },
            position: 'relative'
          }}
        >
          {BackButton}
          <Stack spacing={3} mt={0}>
            <Typography variant="h5" fontWeight={900}>{event.title}</Typography>
            <Stack direction="row" spacing={1} alignItems="center">
              {event.event_type && (
                <Chip label={event.event_type} color="primary" sx={{ fontWeight: 600, fontSize: 15 }} />
              )}
              <Chip
                icon={<PeopleAltIcon sx={{ color: '#1976d2' }} />}
                label={`Участников: ${event.participant_count || 0}`}
                sx={{ fontWeight: 500, fontSize: 14 }}
              />
            </Stack>
            <Typography variant="body1" fontWeight={600}>{event.description}</Typography>
            <Box>
              <Typography variant="subtitle1" fontWeight={600}>Место: <b>{event.location}</b></Typography>
              <Typography variant="subtitle1">
                Дата: <b>{formatDateSafe(event.starts_at)} — {formatDateSafe(event.ends_at)}</b>
              </Typography>
              {event.speaker && <Typography variant="subtitle1">Спикер: <b>{event.speaker}</b></Typography>}
            </Box>
            {imageUrl && (
              <Box
                component="img"
                src={imageUrl}
                alt="Изображение мероприятия"
                loading="lazy"
                sx={{
                  width: '100%',
                  maxHeight: 350,
                  borderRadius: 3,
                  objectFit: 'cover',
                  border: '1px solid #282c34',
                  boxShadow: 2
                }}
                onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
              />
            )}
            <Box>
              <Stack direction="row" spacing={1} alignItems="center" mb={1}>
                <Typography
                  ref={aboutSectionRef}
                  tabIndex={-1}
                  variant="h6"
                  fontWeight={700}
                >
                  Описание мероприятия
                </Typography>
                {(user?.role === 'admin' || user?.role === 'teacher') && !editingAbout && (
                  <IconButton aria-label="Редактировать описание" size="small" onClick={handleEditAbout}>
                    <EditIcon fontSize="small" />
                  </IconButton>
                )}
              </Stack>
              {editingAbout ? (
                <Stack spacing={1}>
                  <TextField
                    label="Описание мероприятия"
                    multiline
                    minRows={3}
                    value={aboutDraft}
                    onChange={e => setAboutDraft(e.target.value)}
                    fullWidth
                    disabled={savingAbout}
                  />
                  <Stack direction="row" spacing={1}>
                    <Button
                      variant="contained"
                      size="small"
                      startIcon={<SaveIcon />}
                      onClick={handleSaveAbout}
                      disabled={savingAbout || aboutDraft.trim() === (event.about || '')}
                    >
                      {savingAbout ? 'Сохраняю...' : 'Сохранить'}
                    </Button>
                    <Button variant="outlined" size="small" startIcon={<CloseIcon />} onClick={handleCancelAbout} disabled={savingAbout}>
                      Отмена
                    </Button>
                  </Stack>
                </Stack>
              ) : (
                <Typography
                  variant="body2"
                  fontSize={16}
                  sx={{ whiteSpace: 'pre-line', color: event.about ? 'inherit' : 'text.disabled' }}
                >
                  {event.about || 'Описание мероприятия не заполнено.'}
                </Typography>
              )}
            </Box>

            {user && (user.role === 'admin' || user.role === 'teacher') && (
              <Box>
                <form onSubmit={handleFileUpload}>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Button variant="contained" component="label" disabled={fileLoading}>
                      Файл
                      <input
                        type="file"
                        name="file"
                        hidden
                        required
                        ref={fileInputRef}
                        onChange={handleFileChange}
                        disabled={fileLoading}
                      />
                    </Button>
                    <Button variant="outlined" type="submit" disabled={!selectedFile || fileLoading}>
                      {fileLoading ? 'Добавление...' : 'Добавить'}
                    </Button>
                    {selectedFile && (
                      <Typography
                        fontSize={12}
                        sx={{
                          ml: 1,
                          maxWidth: 110,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap'
                        }}
                        title={selectedFile.name}
                      >
                        {selectedFile.name}
                      </Typography>
                    )}
                  </Stack>
                </form>
              </Box>
            )}

            {Array.isArray(event.files) && event.files.length > 0 ? (
              <Box>
                <Typography variant="subtitle1" fontWeight={600}>Файлы:</Typography>
                <Stack spacing={1}>
                  {event.files.map((f: any) =>
                    <Box key={f.id} display="flex" alignItems="center">
                      <a
                        href={resolveMediaUrl(f.file_url, BACKEND_ORIGIN) || '#'}
                        target="_blank"
                        rel="noopener noreferrer"
                        download
                        title={f.description || (f.file_url.split('/').pop())}
                        aria-label={`Скачать файл ${f.description || f.file_url.split('/').pop()}`}
                        style={{ color: '#1976d2', fontWeight: 500, textDecoration: 'underline', flex: 1 }}
                      >
                        {f.description || (f.file_url.split('/').pop())}
                      </a>
                      {(user?.role === 'admin' || user?.role === 'teacher') && (
                        <IconButton
                          aria-label="Удалить файл"
                          color="error"
                          onClick={async () => await handleDeleteFile(f.id)}
                          size="small"
                          sx={{ ml: 1 }}
                        >
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      )}
                    </Box>
                  )}
                </Stack>
              </Box>
            ) : (
              <Typography variant="body2" color="text.secondary">Файлов пока нет</Typography>
            )}
          </Stack>

          <Snackbar open={!!snack} autoHideDuration={2500} onClose={() => setSnack('')} message={snack} />
        </Paper>
      </Layout>
    )
  }

  return (
    <Layout>
      <Paper
        elevation={0}
        sx={{
          width: '100vw',
          minHeight: 'calc(100vh - 56px)',
          bgcolor: 'background.paper',
          borderRadius: 0,
          boxShadow: 'none',
          pl: { xs: 2, sm: 4, md: 5, lg: 8 },
          pr: { xs: 8, sm: 6, md: 7, lg: 10 },
          py: { xs: 2, sm: 2, md: 2, lg: 2 },
          display: 'flex',
          flexDirection: 'column'
        }}
      >
        {BackButton}
        <Stack direction="row" spacing={5} alignItems="flex-start" width="100%">
          <Stack spacing={3} width="45%">
            {imageUrl && (
              <Box
                component="img"
                src={imageUrl}
                alt="Изображение мероприятия"
                loading="lazy"
                sx={{
                  width: '100%',
                  maxHeight: 520,
                  borderRadius: 5,
                  objectFit: 'cover',
                  border: '1px solid #282c34',
                  boxShadow: 3
                }}
                onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
              />
            )}
            <Divider />
            <Stack direction="row" spacing={1} alignItems="center" mb={1}>
              <Typography
                ref={aboutSectionRef}
                tabIndex={-1}
                variant="h5"
                fontWeight={700}
              >
                Описание мероприятия
              </Typography>
              {(user?.role === 'admin' || user?.role === 'teacher') && !editingAbout && (
                <IconButton aria-label="Редактировать описание" size="small" onClick={handleEditAbout}>
                  <EditIcon fontSize="small" />
                </IconButton>
              )}
            </Stack>
            {editingAbout ? (
              <Stack spacing={1}>
                <TextField
                  label="Описание мероприятия"
                  multiline
                  minRows={3}
                  value={aboutDraft}
                  onChange={e => setAboutDraft(e.target.value)}
                  fullWidth
                  disabled={savingAbout}
                />
                <Stack direction="row" spacing={1}>
                  <Button
                    variant="contained"
                    size="small"
                    startIcon={<SaveIcon />}
                    onClick={handleSaveAbout}
                    disabled={savingAbout || aboutDraft.trim() === (event.about || '')}
                  >
                    {savingAbout ? 'Сохраняю...' : 'Сохранить'}
                  </Button>
                  <Button variant="outlined" size="small" startIcon={<CloseIcon />} onClick={handleCancelAbout} disabled={savingAbout}>
                    Отмена
                  </Button>
                </Stack>
              </Stack>
            ) : (
              <Typography
                variant="body1"
                fontSize={18}
                sx={{ whiteSpace: 'pre-line', color: event.about ? 'inherit' : 'text.disabled' }}
              >
                {event.about || 'Описание мероприятия не заполнено.'}
              </Typography>
            )}
          </Stack>

          <Stack spacing={2} flex={1} minWidth={0}>
            <Typography variant="h3" fontWeight={900}>{event.title}</Typography>
            <Stack direction="row" spacing={2} alignItems="center">
              {event.event_type && (
                <Chip label={event.event_type} color="primary" sx={{ fontWeight: 600, fontSize: 17 }} />
              )}
              <Chip
                icon={<PeopleAltIcon sx={{ color: '#1976d2' }} />}
                label={`Участников: ${event.participant_count || 0}`}
                sx={{ fontWeight: 500, fontSize: 16 }}
              />
            </Stack>
            <Divider />
            <Typography variant="body1" fontSize={20} fontWeight={600} sx={{ whiteSpace: 'pre-line' }}>
              {event.description}
            </Typography>
            <Divider />
            <Typography variant="subtitle1" fontWeight={600}>Место: <b>{event.location}</b></Typography>
            <Typography variant="subtitle1">
              Дата: <b>{formatDateSafe(event.starts_at)} — {formatDateSafe(event.ends_at)}</b>
            </Typography>
            {event.speaker && <Typography variant="subtitle1">Спикер: <b>{event.speaker}</b></Typography>}

            {user && (user.role === 'admin' || user.role === 'teacher') && (
              <Box mt={2}>
                <form onSubmit={handleFileUpload}>
                  <Stack direction="row" spacing={2} alignItems="center">
                    <Button variant="contained" component="label" disabled={fileLoading}>
                      Файл
                      <input
                        type="file"
                        name="file"
                        hidden
                        required
                        ref={fileInputRef}
                        onChange={handleFileChange}
                        disabled={fileLoading}
                      />
                    </Button>
                    <Button variant="outlined" type="submit" disabled={!selectedFile || fileLoading}>
                      {fileLoading ? 'Добавление...' : 'Добавить'}
                    </Button>
                    {selectedFile && (
                      <Typography
                        fontSize={14}
                        sx={{
                          ml: 2,
                          maxWidth: 150,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap'
                        }}
                        title={selectedFile.name}
                      >
                        {selectedFile.name}
                      </Typography>
                    )}
                  </Stack>
                </form>
              </Box>
            )}

            {Array.isArray(event.files) && event.files.length > 0 ? (
              <Box>
                <Divider sx={{ my: 1 }} />
                <Typography variant="subtitle1" fontWeight={600}>Файлы:</Typography>
                <Stack spacing={1}>
                  {event.files.map((f: any) =>
                    <Box key={f.id} display="flex" alignItems="center">
                      <a
                        href={resolveMediaUrl(f.file_url, BACKEND_ORIGIN) || '#'}
                        target="_blank"
                        rel="noopener noreferrer"
                        download
                        title={f.description || (f.file_url.split('/').pop())}
                        aria-label={`Скачать файл ${f.description || f.file_url.split('/').pop()}`}
                        style={{ color: '#1976d2', fontWeight: 500, textDecoration: 'underline', flex: 1 }}
                      >
                        {f.description || (f.file_url.split('/').pop())}
                      </a>
                      {(user?.role === 'admin' || user?.role === 'teacher') && (
                        <IconButton
                          aria-label="Удалить файл"
                          color="error"
                          onClick={async () => await handleDeleteFile(f.id)}
                          size="small"
                          sx={{ ml: 1 }}
                        >
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      )}
                    </Box>
                  )}
                </Stack>
              </Box>
            ) : (
              <Typography variant="body2" color="text.secondary">Файлов пока нет</Typography>
            )}
          </Stack>
        </Stack>

        <Snackbar open={!!snack} autoHideDuration={2500} onClose={() => setSnack('')} message={snack} />
      </Paper>
    </Layout>
  )
}

export default EventDetail