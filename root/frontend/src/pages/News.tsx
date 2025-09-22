import Layout from "../components/Layout"
import NewsCard from "../components/NewsCard"
import { useEffect, useState, useRef, useCallback, useDeferredValue, startTransition } from "react"
import axios from "../api/axios"
import {
  Box, Typography, Button, Dialog, DialogTitle, DialogContent, Stack, TextField, useMediaQuery
} from "@mui/material"
import ArticleIcon from "@mui/icons-material/Article"
import PhotoCamera from "@mui/icons-material/PhotoCamera"
import { useAuth } from "../contexts/AuthContext"

type NewsItem = {
  id: number
  title: string
  content: string
  image_url?: string
}

const initialNews = { title: "", content: "" }

const News = () => {
  const { user } = useAuth()
  const [newsList, setNewsList] = useState<NewsItem[]>([])
  const deferredList = useDeferredValue(newsList)
  const [visibleCount, setVisibleCount] = useState(0)
  const [addOpen, setAddOpen] = useState(false)
  const [newsData, setNewsData] = useState(initialNews)
  const [adding, setAdding] = useState(false)
  const [loading, setLoading] = useState(false)
  const [imageFile, setImageFile] = useState<File | null>(null)
  const [imagePreview, setImagePreview] = useState<string | null>(null)
  const imageInputRef = useRef<HTMLInputElement | null>(null)
  const isMobile = useMediaQuery("(max-width:600px)")

  const cacheKey = "news:list"
  const etagKey = "news:etag"

  const fetchNews = useCallback(async () => {
    let cancelled = false
    const cached = localStorage.getItem(cacheKey)
    if (cached && newsList.length === 0) {
      try {
        const arr = JSON.parse(cached)
        startTransition(() => setNewsList(Array.isArray(arr) ? arr : []))
      } catch {}
    }
    setLoading(!cached)
    try {
      const etag = localStorage.getItem(etagKey) || ""
      const res = await axios.get("/news", {
        headers: etag ? { "If-None-Match": etag } : {},
        validateStatus: s => s === 200 || s === 304
      })
      if (!cancelled) {
        if (res.status === 200) {
          const arr = Array.isArray(res.data) ? res.data : []
          startTransition(() => setNewsList(arr))
          localStorage.setItem(cacheKey, JSON.stringify(arr))
          const newTag = (res.headers?.etag as string) || ""
          if (newTag) localStorage.setItem(etagKey, newTag)
        } else if (res.status === 304 && cached) {
          try {
            const arr = JSON.parse(cached)
            startTransition(() => setNewsList(Array.isArray(arr) ? arr : []))
          } catch {
            startTransition(() => setNewsList([]))
          }
        }
      }
    } catch {
      if (!cached) startTransition(() => setNewsList([]))
    } finally {
      if (!cancelled) setLoading(false)
    }
    return () => { cancelled = true }
  }, [newsList.length])

  useEffect(() => {
    let cleanup = () => {}
    fetchNews().then((fn) => {
      if (typeof fn === "function") cleanup = fn
    })
    return () => cleanup()
  }, [fetchNews])

  useEffect(() => {
    return () => {
      if (imagePreview) URL.revokeObjectURL(imagePreview)
    }
  }, [imagePreview])

  useEffect(() => {
    setVisibleCount(Math.min(12, deferredList.length))
  }, [deferredList.length])

  useEffect(() => {
    if (visibleCount >= deferredList.length) return
    let cancelled = false
    const chunk = 16
    const ric = (cb: () => void) => {
      if (typeof (window as any).requestIdleCallback === "function") (window as any).requestIdleCallback(() => { if (!cancelled) cb() })
      else setTimeout(() => { if (!cancelled) cb() }, 0)
    }
    const step = () => {
      startTransition(() => {
        setVisibleCount(v => {
          const next = Math.min(v + chunk, deferredList.length)
          if (next < deferredList.length) ric(step)
          return next
        })
      })
    }
    ric(step)
    return () => { cancelled = true }
  }, [visibleCount, deferredList.length])

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      setImageFile(file)
      if (imagePreview) URL.revokeObjectURL(imagePreview)
      setImagePreview(URL.createObjectURL(file))
    }
  }

  const handleAddNews = async () => {
    if (adding) return
    setAdding(true)
    try {
      let image_url = ""
      if (imageFile) {
        const data = new FormData()
        data.append("file", imageFile)
        const res = await axios.post("/news/upload_image", data, {
          headers: { "Content-Type": "multipart/form-data" },
        })
        image_url = res.data?.url || ""
      }

      await axios.post("/news", { ...newsData, image_url })
      setAddOpen(false)
      setNewsData(initialNews)
      setImageFile(null)
      if (imagePreview) {
        URL.revokeObjectURL(imagePreview)
        setImagePreview(null)
      }
      fetchNews()
      if (imageInputRef.current) imageInputRef.current.value = ""
    } finally {
      setAdding(false)
    }
  }

  const handleCloseDialog = () => {
    setAddOpen(false)
    setNewsData(initialNews)
    setImageFile(null)
    if (imagePreview) {
      URL.revokeObjectURL(imagePreview)
      setImagePreview(null)
    }
    if (imageInputRef.current) imageInputRef.current.value = ""
  }

  const visibleList = visibleCount > 0 ? deferredList.slice(0, visibleCount) : deferredList

  return (
    <Layout>
      <Box
        sx={{
          width: "100vw",
          minHeight: "100vh",
          pl: { xs: 2, sm: 4, md: 5, lg: 8 },
          pr: { xs: 4, sm: 6, md: 7, lg: 10 },
          py: { xs: 0, sm: 0, md: 0, lg: 0 },
          boxSizing: "border-box",
          overflowX: "hidden",
        }}
      >
        <Stack
          direction="row"
          alignItems="center"
          gap={2}
          mb={isMobile ? 1.5 : 3}
          mt={isMobile ? 1.5 : 3}
        >
          <ArticleIcon color="primary" sx={{ fontSize: 34 }} />
          <Typography
            variant="h4"
            fontWeight={700}
            color="primary.main"
            sx={{ fontSize: "clamp(0.8rem, 5vw, 2.7rem)" }}
          >
            Новости Университета
          </Typography>
        </Stack>

        {user?.role === "admin" && (
          <Box sx={{ display: "flex", justifyContent: "flex-start", mb: 2 }}>
            <Button
              variant="contained"
              sx={{
                fontWeight: 700,
                fontSize: "clamp(1rem, 2.1vw, 1.15rem)",
                px: { xs: 2.3, sm: 3 },
                py: 1.2,
                borderRadius: 3,
                letterSpacing: "0.02ем",
              }}
              onClick={() => setAddOpen(true)}
              disabled={adding}
            >
              + Добавить новость
            </Button>
          </Box>
        )}

        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
            gap: { xs: 2, sm: 3 },
          }}
        >
          {Array.isArray(visibleList) &&
            visibleList.map((news) => (
              <Box key={news.id} sx={{ display: "flex", width: "100%", height: "100%" }}>
                <NewsCard {...news} onChange={fetchNews} />
              </Box>
            ))}

          {Array.isArray(newsList) && newsList.length === 0 && !loading && (
            <Box sx={{ width: "100%", textAlign: "center", mt: 7, mb: 7 }}>
              <Typography fontSize={24} className="events-empty-text">
                Нет новостей
              </Typography>
            </Box>
          )}
        </Box>

        <Dialog
          open={addOpen}
          onClose={handleCloseDialog}
          fullScreen={isMobile}
          PaperProps={{
            sx: {
              borderRadius: { xs: 0, sm: 4 },
              width: { xs: "100vw", sm: 400 },
              maxWidth: { xs: "100vw", sm: 440 },
            },
          }}
        >
          <DialogTitle sx={{ fontWeight: 700, fontSize: "1.3rem" }}>
            Добавить новость
          </DialogTitle>
          <DialogContent>
            <Stack spacing={2} mt={1} minWidth={isMobile ? "auto" : 340} mb={2}>
              <TextField
                label="Заголовок"
                value={newsData.title}
                onChange={(e) =>
                  setNewsData({ ...newsData, title: e.target.value })
                }
                fullWidth
                inputProps={{ maxLength: 100 }}
                sx={{ fontSize: "1rem" }}
                disabled={adding}
              />
              <TextField
                label="Текст новости"
                value={newsData.content}
                onChange={(e) =>
                  setNewsData({ ...newsData, content: e.target.value })
                }
                multiline
                minRows={5}
                fullWidth
                inputProps={{ maxLength: 3000 }}
                sx={{ fontSize: "1rem" }}
                disabled={adding}
              />

              <Box display="flex" alignItems="center" gap={2}>
                <Button
                  component="label"
                  variant="outlined"
                  startIcon={<PhotoCamera />}
                  sx={{
                    minWidth: 120,
                    fontWeight: 600,
                    fontSize: "1rem",
                    borderRadius: 2,
                  }}
                  disabled={adding}
                >
                  {imageFile ? "Изменить фото" : "Загрузить фото"}
                  <input
                    type="file"
                    accept="image/*"
                    hidden
                    ref={imageInputRef}
                    onChange={handleImageChange}
                  />
                </Button>

                {imagePreview && (
                  <img
                    src={imagePreview}
                    alt="preview"
                    loading="lazy"
                    style={{
                      width: 100,
                      height: 60,
                      objectFit: "cover",
                      borderRadius: 8,
                      border: "1px solid #eee",
                    }}
                  />
                )}
              </Box>

              <Stack direction="row" gap={2} mt={2}>
                <Button
                  variant="contained"
                  onClick={handleAddNews}
                  disabled={
                    !newsData.title.trim() ||
                    !newsData.content.trim() ||
                    adding
                  }
                  sx={{
                    fontWeight: 700,
                    borderRadius: 2.2,
                    px: 3,
                    fontSize: "1.02rem",
                  }}
                >
                  {adding ? "Публикую..." : "Опубликовать"}
                </Button>
                <Button
                  variant="outlined"
                  color="secondary"
                  onClick={handleCloseDialog}
                  disabled={adding}
                  sx={{ borderRadius: 2.2, px: 2.5, fontSize: "1.02rem" }}
                >
                  Отмена
                </Button>
              </Stack>
            </Stack>
          </DialogContent>
        </Dialog>
      </Box>
    </Layout>
  )
}

export default News