import Layout from "../components/Layout"
import PageFadeIn from "../components/PageFadeIn"
import NewsCard from "../components/NewsCard"
import NewsCardSkeleton from "../components/NewsCardSkeleton"
import {
  useEffect,
  useState,
  useRef,
  useCallback,
  useDeferredValue,
  startTransition,
  useMemo,
  type ReactNode,
} from "react"
import { createNews, uploadNewsImage } from "@/api/news"
import ArticleIcon from "@mui/icons-material/Article"
import PhotoCamera from "@mui/icons-material/PhotoCamera"
import SmartImage from "@/components/SmartImage"
import { Button } from "@/components/ui"
import Dialog from "@/components/Dialog"
import { useAuth } from "../contexts/AuthContext"
import { useLanguage } from "../contexts/LanguageContext"
import { useTranslation } from "react-i18next"
import { useNewsFeed } from "@/hooks/useNewsFeed"

const inputClass =
  "w-full rounded-ue-lg border border-white/12 bg-[color:color-mix(in_srgb,var(--card-bg)_94%,white_6%)] px-4 py-2.5 text-[0.98rem] text-[color:var(--page-text)] shadow-[inset_0_1px_0_rgba(15,23,42,0.08)] transition focus:border-[color:var(--nav-link)] focus:outline-none focus:shadow-focus placeholder:text-[color:var(--placeholder-fg)]"
const textareaClass = `${inputClass} min-h-[148px] resize-y leading-relaxed`

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

type FieldProps = {
  label: ReactNode
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
  const titleInputRef = useRef<HTMLInputElement | null>(null)

  const isInitialLoading = isPending && newsList.length === 0
  const showEmptyState = !isInitialLoading && !isFetching && newsList.length === 0
  const skeletonCount = Math.max(visibleCount || 0, 6)

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
        <div className="flex w-full flex-col px-4 pb-16 pt-6 sm:px-6 lg:px-8">
          <div
            data-fade
            className="mb-4 mt-4 flex flex-wrap items-center gap-3 text-nav-link [--fade-delay:80ms] sm:mb-8 sm:mt-6"
          >
            <span className="inline-flex h-11 w-11 items-center justify-center rounded-full bg-[color:var(--glass-bg)]/70 text-[color:var(--nav-link)] shadow-surface">
              <ArticleIcon className="text-[1.85rem]" />
            </span>
            <h1 className="text-[clamp(1.6rem,5vw,2.75rem)] font-bold tracking-tight text-[color:var(--page-text)]">
              {t("news:pageTitle")}
            </h1>
          </div>

          {user?.role === "admin" && (
            <div
              data-fade
              className="mb-6 flex justify-start [--fade-delay:140ms]"
            >
              <Button
                size="lg"
                onClick={() => setAddOpen(true)}
                disabled={adding}
                className="px-6 text-[clamp(1rem,2.2vw,1.1rem)]"
              >
                {t("news:actions.add")}
              </Button>
            </div>
          )}

          <div
            data-fade
            className="grid grid-cols-[repeat(auto-fit,minmax(310px,1fr))] gap-5 [--fade-delay:200ms] sm:gap-6"
          >
            {isInitialLoading
              ? Array.from({ length: skeletonCount }).map((_, index) => (
                  <div key={`news-skeleton-${index}`} className="flex h-full w-full">
                    <NewsCardSkeleton />
                  </div>
                ))
              : Array.isArray(visibleList) &&
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

            {showEmptyState && (
              <div className="col-span-full mt-16 flex justify-start">
                <div className="flex w-full max-w-[420px] flex-col items-center gap-5 rounded-ue-xl border border-white/12 bg-glass/60 px-6 py-10 text-center text-[color:var(--secondary-text)] shadow-surface">
                  <span className="flex h-16 w-16 items-center justify-center rounded-full bg-[color:var(--glass-bg)]/70 text-[color:var(--nav-link)] shadow-surface">
                    <ArticleIcon className="text-[2.2rem]" />
                  </span>
                  <p className="text-lg font-semibold text-[color:var(--page-text)] sm:text-xl">
                    {t("news:states.empty")}
                  </p>
                  {user?.role === "admin" && (
                    <Button size="lg" onClick={() => setAddOpen(true)} className="px-6">
                      {t("news:actions.add")}
                    </Button>
                  )}
                </div>
              </div>
            )}
          </div>

          <Dialog
            open={addOpen}
            onClose={handleCloseDialog}
            title={t("news:dialogs.create.title")}
            size="md"
            fullScreenOnMobile
            closeLabel={t("common:buttons.close")}
            bodyClassName="space-y-4"
            footerClassName="flex-col-reverse gap-3 sm:flex-row"
            footer={
              <>
                <Button
                  variant="outline"
                  onClick={handleCloseDialog}
                  disabled={adding}
                  className="w-full sm:w-auto"
                >
                  {t("common:buttons.cancel")}
                </Button>
                <Button
                  onClick={() => {
                    void handleAddNews()
                  }}
                  disabled={!newsData.title.trim() || !newsData.content.trim() || adding}
                  loading={adding}
                  className="w-full sm:w-auto"
                >
                  {adding ? t("common:statuses.publishing") : t("news:actions.publish")}
                </Button>
              </>
            }
            initialFocus={() => titleInputRef.current ?? undefined}
          >
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault()
                void handleAddNews()
              }}
            >
              <Field label={t("news:form.title") ?? ""} htmlFor="news-title" required>
                <input
                  id="news-title"
                  ref={titleInputRef}
                  type="text"
                  value={newsData.title}
                  onChange={(e) => setNewsData({ ...newsData, title: e.target.value })}
                  maxLength={100}
                  disabled={adding}
                  className={inputClass}
                />
              </Field>

              <Field label={t("news:form.content") ?? ""} htmlFor="news-content" required>
                <textarea
                  id="news-content"
                  value={newsData.content}
                  onChange={(e) => setNewsData({ ...newsData, content: e.target.value })}
                  maxLength={3000}
                  disabled={adding}
                  className={textareaClass}
                  rows={6}
                />
              </Field>

              <Field
                label={t("news:form.title_en", { defaultValue: "Title (English)" }) ?? ""}
                htmlFor="news-title-en"
              >
                <input
                  id="news-title-en"
                  type="text"
                  value={newsData.title_en}
                  onChange={(e) => setNewsData({ ...newsData, title_en: e.target.value })}
                  maxLength={100}
                  disabled={adding}
                  className={inputClass}
                />
              </Field>

              <Field
                label={t("news:form.content_en", { defaultValue: "News text (English)" }) ?? ""}
                htmlFor="news-content-en"
              >
                <textarea
                  id="news-content-en"
                  value={newsData.content_en}
                  onChange={(e) => setNewsData({ ...newsData, content_en: e.target.value })}
                  maxLength={3000}
                  disabled={adding}
                  className={textareaClass}
                  rows={6}
                />
              </Field>

              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <Button
                  as="label"
                  variant="outline"
                  size="sm"
                  leadingIcon={<PhotoCamera className="text-[1.15rem]" />}
                  className="w-full sm:w-auto"
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

                {imagePreview ? (
                  <SmartImage
                    srcRaw={imagePreview}
                    alt={t("news:alt.newCover")}
                    className="h-20 w-full max-w-[160px] rounded-ue-md border border-white/10 object-cover shadow-surface"
                  />
                ) : null}
              </div>
            </form>
          </Dialog>
        </div>
      </PageFadeIn>
    </Layout>
  )
}

export default News
