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
import { Button } from "@/components/ui/button"
import {
  Modal,
  ModalBody,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalTitle,
  ModalCloseButton,
} from "@/components/ui/modal"
import { TextArea, TextInput } from "@/components/ui/input"
import useMediaQuery from "@/hooks/useMediaQuery"
import { cn } from "@/utils/cn"
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

  const openImagePicker = useCallback(() => {
    if (adding) return
    imageInputRef.current?.click()
  }, [adding])

  const visibleList = useMemo(
    () => (visibleCount > 0 ? deferredList.slice(0, visibleCount) : deferredList),
    [deferredList, visibleCount]
  )

  return (
    <Layout>
      <PageFadeIn>
        <section className="relative w-full overflow-x-hidden bg-transparent">
          <div className="mx-auto flex min-h-screen w-full max-w-6xl flex-col px-4 pb-16 pt-6 sm:px-6 md:px-10 lg:px-16">
            <header
              data-fade
              style={{ "--fade-delay": "80ms" } as CSSProperties}
              className="group mb-6 flex items-center gap-4 rounded-ue-xl border border-[color:var(--glass-border)] bg-[color:var(--card-bg)]/75 p-4 shadow-surface backdrop-blur supports-[backdrop-filter]:backdrop-blur-md"
            >
              <span className="flex h-12 w-12 items-center justify-center rounded-full bg-[color:var(--surface-accent,#111827)]/60 text-[color:var(--nav-link)] shadow-inner">
                <ArticleIcon style={{ fontSize: "1.8rem" }} />
              </span>
              <h1 className="font-display text-[clamp(1.4rem,4vw,2.6rem)] font-semibold tracking-tight text-[color:var(--page-text)]">
                {t("news:pageTitle")}
              </h1>
            </header>

            {user?.role === "admin" && (
              <div
                data-fade
                style={{ "--fade-delay": "140ms" } as CSSProperties}
                className="mb-2 flex justify-start"
              >
                <Button
                  size="md"
                  className="rounded-ue-lg px-5 font-semibold tracking-tight shadow-surface transition-transform duration-300 hover:-translate-y-[2px] focus-visible:shadow-focus"
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
              className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-3"
            >
              {Array.isArray(visibleList) &&
                visibleList.map((news) => (
                  <div key={news.id} className="flex">
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
                <div className="col-span-full">
                  <div className="flex flex-col items-center justify-center gap-3 rounded-ue-xl border border-dashed border-[color:var(--glass-border)]/70 bg-[color:var(--card-bg)]/60 px-6 py-16 text-center text-[color:var(--secondary-text)] shadow-surface">
                    <ArticleIcon style={{ fontSize: "2rem", color: "var(--secondary-text)" }} aria-hidden="true" />
                    <p className="text-lg font-medium tracking-tight">{t("news:states.empty")}</p>
                  </div>
                </div>
              )}
            </div>
          </div>

          <Modal
            open={addOpen}
            onOpenChange={(open) => {
              if (open) {
                setAddOpen(true)
                return
              }
              handleCloseDialog()
            }}
            className={cn("p-4 sm:p-8", isMobile && "p-0")}
            overlayClassName="backdrop-blur"
          >
            <ModalContent
              hideScrollbars={isMobile}
              className={cn(
                "w-full max-w-xl border border-[color:var(--glass-border)] bg-[color:var(--card-bg)]/98 shadow-surface-strong",
                isMobile && "h-screen max-h-none rounded-none border-none"
              )}
            >
              <ModalHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <ModalTitle className="text-[clamp(1.25rem,2.4vw,1.6rem)] font-semibold text-[color:var(--page-text)]">
                  {t("news:dialogs.create.title")}
                </ModalTitle>
                <ModalCloseButton className="self-start sm:self-center">
                  {t("common:buttons.close")}
                </ModalCloseButton>
              </ModalHeader>
              <ModalBody className="gap-5">
                <TextInput
                  label={t("news:form.title")}
                  value={newsData.title}
                  onChange={(e) => setNewsData({ ...newsData, title: e.target.value })}
                  maxLength={100}
                  disabled={adding}
                  required
                />
                <TextArea
                  label={t("news:form.content")}
                  value={newsData.content}
                  onChange={(e) => setNewsData({ ...newsData, content: e.target.value })}
                  rows={5}
                  maxLength={3000}
                  disabled={adding}
                  required
                />
                <TextInput
                  label={t("news:form.title_en", { defaultValue: "Title (English)" })}
                  value={newsData.title_en}
                  onChange={(e) => setNewsData({ ...newsData, title_en: e.target.value })}
                  maxLength={100}
                  disabled={adding}
                />
                <TextArea
                  label={t("news:form.content_en", { defaultValue: "News text (English)" })}
                  value={newsData.content_en}
                  onChange={(e) => setNewsData({ ...newsData, content_en: e.target.value })}
                  rows={5}
                  maxLength={3000}
                  disabled={adding}
                />

                <div className="rounded-ue-xl border border-dashed border-[color:var(--glass-border)]/70 bg-[color:var(--card-bg)]/60 p-4">
                  <input
                    id="news-image-upload"
                    type="file"
                    accept="image/*"
                    className="sr-only"
                    ref={imageInputRef}
                    onChange={handleImageChange}
                    aria-label={t("news:form.imageUpload", { defaultValue: "Upload cover image" })}
                  />
                  <div className="flex flex-wrap items-center gap-4">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="cursor-pointer rounded-ue-lg px-4 font-semibold tracking-tight"
                      disabled={adding}
                      onClick={openImagePicker}
                    >
                      <span className="inline-flex items-center gap-2">
                        <PhotoCamera fontSize="small" />
                        <span>
                          {imageFile
                            ? t("common:buttons.changePhoto")
                            : t("common:buttons.uploadPhoto")}
                        </span>
                      </span>
                    </Button>

                    {imagePreview ? (
                      <div className="relative h-20 w-32 overflow-hidden rounded-ue-lg border border-[color:var(--glass-border)] shadow-surface">
                        <SmartImage
                          srcRaw={imagePreview}
                          alt={t("news:alt.newCover")}
                          className="h-full w-full object-cover"
                        />
                      </div>
                    ) : (
                      <p className="text-sm text-[color:var(--secondary-text)]">
                        {t("news:form.imageHelper", {
                          defaultValue: "Upload a landscape image to feature alongside your post.",
                        })}
                      </p>
                    )}
                  </div>
                </div>
              </ModalBody>
              <ModalFooter>
                <Button
                  variant="outline"
                  onClick={handleCloseDialog}
                  disabled={adding}
                  className="rounded-ue-lg px-5"
                >
                  {t("common:buttons.cancel")}
                </Button>
                <Button
                  onClick={handleAddNews}
                  loading={adding}
                  disabled={!newsData.title.trim() || !newsData.content.trim() || adding}
                  className="rounded-ue-lg px-6"
                >
                  {adding ? t("common:statuses.publishing") : t("news:actions.publish")}
                </Button>
              </ModalFooter>
            </ModalContent>
          </Modal>
        </section>
      </PageFadeIn>
    </Layout>
  )
}

export default News
