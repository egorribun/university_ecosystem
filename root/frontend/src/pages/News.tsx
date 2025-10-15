import Layout from "../components/Layout"
import PageFadeIn from "../components/PageFadeIn"
import NewsCard from "../components/NewsCard"
import {
  useEffect,
  useState,
  useRef,
  useCallback,
  useDeferredValue,
  startTransition,
  useMemo,
  type CSSProperties,
} from "react"
import axios from "../api/client"
import {
  Box, Typography, Button, Dialog, DialogTitle, DialogContent, Stack, TextField, useMediaQuery
} from "@mui/material"
import ArticleIcon from "@mui/icons-material/Article"
import PhotoCamera from "@mui/icons-material/PhotoCamera"
import SmartImage from "@/components/SmartImage"
import { useAuth } from "../contexts/AuthContext"
import { useLanguage } from "../contexts/LanguageContext"
import { useTranslation } from "react-i18next"

type NewsItem = {
  id: number
  title: string
  content: string
  title_en?: string | null
  content_en?: string | null
  created_at: string
  image_url?: string | null
}

const isNewsItem = (value: unknown): value is NewsItem => {
  if (!value || typeof value !== "object") return false
  const obj = value as Record<string, unknown>
  return (
    typeof obj.id === "number" &&
    typeof obj.title === "string" &&
    typeof obj.content === "string" &&
    typeof obj.created_at === "string"
  )
}

const toNewsList = (value: unknown): NewsItem[] => (Array.isArray(value) ? value.filter(isNewsItem) : [])

type NewsFormState = {
  title: string
  content: string
  title_en: string
  content_en: string
}

const initialNews: NewsFormState = {
  title: "",
  content: "",
  title_en: "",
  content_en: "",
}

const News = () => {
  const { user } = useAuth()
  const { t } = useTranslation(["news", "common"])
  const { language } = useLanguage()
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
  const hydratedFromCache = useRef(false)
  const isMobile = useMediaQuery("(max-width:600px)")

  const cacheKey = useMemo(() => `news:list:${language}`, [language])
  const etagKey = useMemo(() => `news:etag:${language}`, [language])
  const legacyCacheKey = "news:list"
  const legacyEtagKey = "news:etag"

  const fetchNews = useCallback(
    async (signal?: AbortSignal) => {
      const cachedPrimary = localStorage.getItem(cacheKey)
      const cachedLegacy = language === "ru" ? localStorage.getItem(legacyCacheKey) : null
      const cached = cachedPrimary ?? cachedLegacy

      if (cached && !hydratedFromCache.current) {
        try {
          const arr = toNewsList(JSON.parse(cached))
          startTransition(() => setNewsList(arr))
          hydratedFromCache.current = true
        } catch {}
      }

      const shouldShowLoader = !cached && !hydratedFromCache.current
      if (shouldShowLoader) setLoading(true)

      try {
        const storedTagPrimary = localStorage.getItem(etagKey)
        const storedTagLegacy = language === "ru" ? localStorage.getItem(legacyEtagKey) : null
        const etag = storedTagPrimary ?? storedTagLegacy ?? ""
        const res = await axios.get<NewsItem[]>("/news", {
          headers: {
            ...(etag ? { "If-None-Match": etag } : {}),
            "Accept-Language": language,
          },
          signal,
          validateStatus: (s) => s === 200 || s === 304,
        })

        if (signal?.aborted) return

        if (res.status === 200) {
          const arr = toNewsList(res.data)
          startTransition(() => setNewsList(arr))
          hydratedFromCache.current = true
          localStorage.setItem(cacheKey, JSON.stringify(arr))
          if (language === "ru") localStorage.setItem(legacyCacheKey, JSON.stringify(arr))
          const newTag = (res.headers?.etag as string) || ""
          if (newTag) {
            localStorage.setItem(etagKey, newTag)
            if (language === "ru") localStorage.setItem(legacyEtagKey, newTag)
          }
        } else if (res.status === 304 && cached) {
          try {
            const arr = toNewsList(JSON.parse(cached))
            startTransition(() => setNewsList(arr))
            hydratedFromCache.current = true
          } catch {
            startTransition(() => setNewsList([]))
          }
        }
      } catch {
        if (signal?.aborted) return
        if (!cached) startTransition(() => setNewsList([]))
      } finally {
        if (signal?.aborted) return
        if (shouldShowLoader) setLoading(false)
      }
    },
    [cacheKey, etagKey, language, legacyCacheKey, legacyEtagKey],
  )

  useEffect(() => {
    const controller = new AbortController()
    void fetchNews(controller.signal)
    return () => controller.abort()
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

  const handleImageChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      setImageFile(file)
      if (imagePreview) URL.revokeObjectURL(imagePreview)
      setImagePreview(URL.createObjectURL(file))
    }
  }, [imagePreview])

  const handleAddNews = useCallback(async () => {
    if (adding) return
    setAdding(true)
    try {
      let image_url = ""
      if (imageFile) {
        const data = new FormData()
        data.append("file", imageFile)
        const res = await axios.post<{ url: string }>("/news/upload_image", data, {
          headers: { "Content-Type": "multipart/form-data" },
        })
        image_url = res.data?.url || ""
      }

      const payload = {
        title: newsData.title,
        content: newsData.content,
        image_url,
        ...(newsData.title_en.trim() ? { title_en: newsData.title_en } : {}),
        ...(newsData.content_en.trim() ? { content_en: newsData.content_en } : {}),
      }

      await axios.post("/news", payload, {
        headers: { "Accept-Language": language },
      })
      setAddOpen(false)
      setNewsData(initialNews)
      setImageFile(null)
      if (imagePreview) {
        URL.revokeObjectURL(imagePreview)
        setImagePreview(null)
      }
      void fetchNews()
      if (imageInputRef.current) imageInputRef.current.value = ""
    } finally {
      setAdding(false)
    }
  }, [adding, fetchNews, imageFile, imagePreview, language, newsData])

  const handleCloseDialog = useCallback(() => {
    setAddOpen(false)
    setNewsData(initialNews)
    setImageFile(null)
    if (imagePreview) {
      URL.revokeObjectURL(imagePreview)
      setImagePreview(null)
    }
    if (imageInputRef.current) imageInputRef.current.value = ""
  }, [imagePreview])

  const visibleList = useMemo(
    () => (visibleCount > 0 ? deferredList.slice(0, visibleCount) : deferredList),
    [deferredList, visibleCount],
  )

  return (
    <Layout>
      <PageFadeIn>
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
            data-fade
            style={{ '--fade-delay': '80ms' } as CSSProperties }
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
              {t("news:pageTitle")}
            </Typography>
          </Stack>

        {user?.role === "admin" && (
          <Box
            data-fade
            style={{ '--fade-delay': '140ms' } as CSSProperties }
            sx={{ display: "flex", justifyContent: "flex-start", mb: 2 }}>
            <Button
              variant="contained"
              sx={{
                fontWeight: 700,
                fontSize: "clamp(1rem, 2.1vw, 1.15rem)",
                px: { xs: 2.3, sm: 3 },
                py: 1.2,
                borderRadius: 3,
                letterSpacing: "0.02em",
              }}
              onClick={() => setAddOpen(true)}
              disabled={adding}
            >
              {t("news:actions.add")}
            </Button>
          </Box>
        )}

          <Box
            data-fade
          style={{ '--fade-delay': '200ms' } as CSSProperties }
          sx={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
            gap: { xs: 2, sm: 3 },
          }}
        >
          {Array.isArray(visibleList) &&
            visibleList.map((news) => (
              <Box key={news.id} sx={{ display: "flex", width: "100%", height: "100%" }}>
                <NewsCard
                  {...news}
                  image_url={news.image_url ?? undefined}
                  onChange={() => {
                    void fetchNews()
                  }}
                />
              </Box>
            ))}

          {Array.isArray(newsList) && newsList.length === 0 && !loading && (
            <Box sx={{ width: "100%", textAlign: "center", mt: 7, mb: 7 }}>
              <Typography fontSize={24} className="events-empty-text">
                {t("news:states.empty")}
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
            {t("news:dialogs.create.title")}
          </DialogTitle>
          <DialogContent>
            <Stack spacing={2} mt={1} minWidth={isMobile ? "auto" : 340} mb={2}>
              <TextField
                label={t("news:form.title")}
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
                label={t("news:form.content")}
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
              <TextField
                label={t("news:form.title_en", { defaultValue: "Title (English)" })}
                value={newsData.title_en}
                onChange={(e) =>
                  setNewsData({ ...newsData, title_en: e.target.value })
                }
                fullWidth
                inputProps={{ maxLength: 100 }}
                sx={{ fontSize: "1rem" }}
                disabled={adding}
              />
              <TextField
                label={t("news:form.content_en", { defaultValue: "News text (English)" })}
                value={newsData.content_en}
                onChange={(e) =>
                  setNewsData({ ...newsData, content_en: e.target.value })
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
                  {imageFile ? t("common:buttons.changePhoto") : t("common:buttons.uploadPhoto")}
                  <input
                    type="file"
                    accept="image/*"
                    hidden
                    ref={imageInputRef}
                    onChange={handleImageChange}
                  />
                </Button>

                {imagePreview && (
                  <SmartImage
                    srcRaw={imagePreview}
                    alt={t("news:alt.newCover")}
                    style={{
                      width: 100,
                      height: 60,
                      objectFit: "cover",
                      borderRadius: 8,
                      border: "1px solid #eee",
                      display: "block",
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
                  {adding ? t("common:statuses.publishing") : t("news:actions.publish")}
                </Button>
                <Button
                  variant="outlined"
                  color="secondary"
                  onClick={handleCloseDialog}
                  disabled={adding}
                  sx={{ borderRadius: 2.2, px: 2.5, fontSize: "1.02rem" }}
                >
                  {t("common:buttons.cancel")}
                </Button>
              </Stack>
            </Stack>
          </DialogContent>
        </Dialog>
      </Box>
      </PageFadeIn>
    </Layout>
  )
}

export default News