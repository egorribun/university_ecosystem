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
import { createNews, uploadNewsImage } from "@/api/news"
import {
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  TextField,
  useMediaQuery,
} from "@mui/material"
import ArticleIcon from "@mui/icons-material/Article"
import PhotoCamera from "@mui/icons-material/PhotoCamera"
import SmartImage from "@/components/SmartImage"
import { useAuth } from "../contexts/AuthContext"
import { useLanguage } from "../contexts/LanguageContext"
import { useTranslation } from "react-i18next"
import { useNewsFeed } from "@/hooks/useNewsFeed"

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
  const { data: newsDataList, refetch: refetchNews, isPending, isFetching } = useNewsFeed(language)
  const newsList = newsDataList ?? []
  const deferredList = useDeferredValue(newsList)
  const [visibleCount, setVisibleCount] = useState(0)
  const [addOpen, setAddOpen] = useState(false)
  const [newsData, setNewsData] = useState(initialNews)
  const [adding, setAdding] = useState(false)
  const [imageFile, setImageFile] = useState<File | null>(null)
  const [imagePreview, setImagePreview] = useState<string | null>(null)
  const imageInputRef = useRef<HTMLInputElement | null>(null)
  const isMobile = useMediaQuery("(max-width:600px)")

  const isInitialLoading = isPending && newsList.length === 0
  const showEmptyState = !isInitialLoading && !isFetching && newsList.length === 0

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
      if (typeof (window as any).requestIdleCallback === "function")
        (window as any).requestIdleCallback(() => {
          if (!cancelled) cb()
        })
      else
        setTimeout(() => {
          if (!cancelled) cb()
        }, 0)
    }
    const step = () => {
      startTransition(() => {
        setVisibleCount((v) => {
          const next = Math.min(v + chunk, deferredList.length)
          if (next < deferredList.length) ric(step)
          return next
        })
      })
    }
    ric(step)
    return () => {
      cancelled = true
    }
  }, [visibleCount, deferredList.length])

  const handleImageChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file) {
        setImageFile(file)
        if (imagePreview) URL.revokeObjectURL(imagePreview)
        setImagePreview(URL.createObjectURL(file))
      }
    },
    [imagePreview]
  )

  const handleAddNews = useCallback(async () => {
    if (adding) return
    setAdding(true)
    try {
      let image_url = ""
      if (imageFile) {
        const uploadedUrl = await uploadNewsImage(imageFile)
        image_url = uploadedUrl || ""
      }

      const payload = {
        title: newsData.title,
        content: newsData.content,
        image_url,
        ...(newsData.title_en.trim() ? { title_en: newsData.title_en } : {}),
        ...(newsData.content_en.trim() ? { content_en: newsData.content_en } : {}),
      } satisfies Parameters<typeof createNews>[0]

      await createNews(payload)
      setAddOpen(false)
      setNewsData(initialNews)
      setImageFile(null)
      if (imagePreview) {
        URL.revokeObjectURL(imagePreview)
        setImagePreview(null)
      }
      void refetchNews()
      if (imageInputRef.current) imageInputRef.current.value = ""
    } finally {
      setAdding(false)
    }
  }, [adding, imageFile, imagePreview, newsData, refetchNews])

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
    [deferredList, visibleCount]
  )

  return (
    <Layout>
      <PageFadeIn>
        <div className="w-screen min-h-screen overflow-x-hidden px-4 sm:px-6 md:px-8 lg:px-12">
          <div className="mx-auto flex w-full max-w-6xl flex-col">
            <div
              data-fade
              style={{ "--fade-delay": "80ms" } as CSSProperties}
              className={`flex items-center gap-3 md:gap-4 ${
                isMobile ? "my-6" : "my-10"
              }`}
            >
              <ArticleIcon className="h-9 w-9 text-blue-600 md:h-10 md:w-10" />
              <h1 className="font-display text-2xl font-bold tracking-tight text-blue-700 md:text-3xl lg:text-4xl">
                {t("news:pageTitle")}
              </h1>
            </div>

            {user?.role === "admin" && (
              <div
                data-fade
                style={{ "--fade-delay": "140ms" } as CSSProperties}
                className={`flex justify-start ${isMobile ? "mb-4" : "mb-6"}`}
              >
                <Button
                  variant="contained"
                  className="!rounded-full !bg-blue-600 !px-5 !py-3 !text-base !font-semibold !tracking-wide !text-white !shadow-sm transition hover:!bg-blue-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 disabled:!cursor-not-allowed disabled:!bg-blue-300"
                  onClick={() => setAddOpen(true)}
                  disabled={adding}
                >
                  {t("news:actions.add")}
                </Button>
              </div>
            )}

            <div
              data-fade
              style={{ "--fade-delay": "200ms" } as CSSProperties}
              className="grid w-full max-w-6xl gap-4 sm:gap-6 [grid-template-columns:repeat(auto-fit,minmax(320px,1fr))]"
            >
              {Array.isArray(visibleList) &&
                visibleList.map((news) => (
                  <div key={news.id} className="flex h-full w-full">
                    <NewsCard
                      {...news}
                      image_url={news.image_url ?? undefined}
                      onChange={() => {
                        void refetchNews()
                      }}
                    />
                  </div>
                ))}

              {Array.isArray(newsList) && showEmptyState && (
                <div className="col-span-full mt-14 mb-14 text-center">
                  <p className="text-2xl font-semibold text-secondary">
                    {t("news:states.empty")}
                  </p>
                </div>
              )}
            </div>

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
              <DialogTitle className="text-xl font-semibold text-page-foreground md:text-2xl">
                {t("news:dialogs.create.title")}
              </DialogTitle>
              <DialogContent className="pb-6">
                <div className={`mt-2 flex flex-col gap-4 ${isMobile ? "" : "min-w-[340px]"}`}>
                  <TextField
                    label={t("news:form.title")}
                    value={newsData.title}
                    onChange={(e) => setNewsData({ ...newsData, title: e.target.value })}
                    fullWidth
                    inputProps={{ maxLength: 100 }}
                    disabled={adding}
                  />
                  <TextField
                    label={t("news:form.content")}
                    value={newsData.content}
                    onChange={(e) => setNewsData({ ...newsData, content: e.target.value })}
                    multiline
                    minRows={5}
                    fullWidth
                    inputProps={{ maxLength: 3000 }}
                    disabled={adding}
                  />
                  <TextField
                    label={t("news:form.title_en", { defaultValue: "Title (English)" })}
                    value={newsData.title_en}
                    onChange={(e) => setNewsData({ ...newsData, title_en: e.target.value })}
                    fullWidth
                    inputProps={{ maxLength: 100 }}
                    disabled={adding}
                  />
                  <TextField
                    label={t("news:form.content_en", { defaultValue: "News text (English)" })}
                    value={newsData.content_en}
                    onChange={(e) => setNewsData({ ...newsData, content_en: e.target.value })}
                    multiline
                    minRows={5}
                    fullWidth
                    inputProps={{ maxLength: 3000 }}
                    disabled={adding}
                  />

                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                    <Button
                      component="label"
                      variant="outlined"
                      startIcon={<PhotoCamera />}
                      className="!min-w-[120px] !rounded-lg !border-blue-500 !px-4 !py-2.5 !font-semibold !text-blue-600 hover:!border-blue-600 hover:!bg-blue-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 disabled:!cursor-not-allowed"
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
                        className="h-16 w-24 rounded-lg border border-slate-10 object-cover"
                      />
                    )}
                  </div>

                  <div className="mt-2 flex flex-col gap-3 sm:flex-row">
                    <Button
                      variant="contained"
                      onClick={handleAddNews}
                      disabled={!newsData.title.trim() || !newsData.content.trim() || adding}
                      className="!rounded-lg !bg-blue-600 !px-4 !py-2.5 !text-base !font-semibold !text-white !shadow-sm transition hover:!bg-blue-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 disabled:!cursor-not-allowed disabled:!bg-blue-300"
                    >
                      {adding ? t("common:statuses.publishing") : t("news:actions.publish")}
                    </Button>
                    <Button
                      variant="outlined"
                      color="secondary"
                      onClick={handleCloseDialog}
                      disabled={adding}
                      className="!rounded-lg !border-slate-40 !px-4 !py-2.5 !text-base !font-semibold !text-secondary hover:!border-slate-40 hover:!bg-slate-10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 disabled:!cursor-not-allowed"
                    >
                      {t("common:buttons.cancel")}
                    </Button>
                  </div>
                </div>
              </DialogContent>
            </Dialog>
          </div>
        </div>
      </PageFadeIn>
    </Layout>
  )
}

export default News
