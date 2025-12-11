import Layout from "../components/Layout"
import PageFadeIn from "../components/PageFadeIn"
import NewsCard from "../components/NewsCard"
import NewsCardSkeleton from "../components/NewsCardSkeleton"
import {
  useState,
  useRef,
  useCallback,
  type ReactNode,
  type CSSProperties,
} from "react"
import { Alert } from "@mui/material"
import { isAxiosError } from "axios"
import { createNews, uploadNewsImage } from "@/api/news"
import ArticleIcon from "@mui/icons-material/Article"
import PhotoCamera from "@mui/icons-material/PhotoCamera"
import SmartImage from "@/components/SmartImage"
import { Button } from "@/components/ui"
import Dialog from "@/components/Dialog"
import { useAuth } from "../contexts/AuthContext"
import { useLanguage } from "../contexts/LanguageContext"
import { useTranslation } from "react-i18next"
import { useQueryClient } from "@tanstack/react-query"
import { useNewsListQuery } from "@/api/hooks/news"
import { resetEtagCache } from "@/api/client"

const inputClass =
  "w-full rounded-ue-lg border border-white/12 bg-[color:color-mix(in_srgb,var(--card-bg)_94%,white_6%)] px-4 py-2.5 text-[0.98rem] text-[color:var(--page-text)] shadow-[inset_0_1px_0_rgba(15,23,42,0.08)] transition focus:border-[color:var(--nav-link)] focus:outline-none focus:shadow-focus placeholder:text-[color:var(--placeholder-fg)]"
const textareaClass = `${inputClass} min-h-[148px] resize-y leading-relaxed`

const fadeDelayStyle = (value: string): CSSProperties =>
  ({ "--fade-delay": value }) as CSSProperties

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
  const queryClient = useQueryClient()

  // Use the new hook inspired by Events
  const {
    news: newsList,
    isLoading: isInitialLoading,
    isFetching,
    isFetchingNextPage,
    hasNextPage,
    fetchNextPage,
    refetch: refetchNews
  } = useNewsListQuery({ language })

  const [addOpen, setAddOpen] = useState(false)
  const [newsData, setNewsData] = useState(initialNews)
  const [adding, setAdding] = useState(false)
  const [addError, setAddError] = useState<string | null>(null)
  const [imageFile, setImageFile] = useState<File | null>(null)
  const [imagePreview, setImagePreview] = useState<string | null>(null)
  const imageInputRef = useRef<HTMLInputElement | null>(null)
  const titleInputRef = useRef<HTMLInputElement | null>(null)

  const showEmptyState = !isInitialLoading && !isFetching && newsList.length === 0
  const skeletonCount = 6



  const refreshNews = useCallback(() => {
    resetEtagCache()
    void queryClient.invalidateQueries({ queryKey: ["news", "list"] })
  }, [queryClient])

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

  const resolveCreateError = useCallback(
    (error: unknown) => {
      const fallback =
        t("news:notifications.savedError", { defaultValue: "Failed to save the news" }) ??
        "Failed to save the news"

      if (isAxiosError(error)) {
        const data = error.response?.data
        if (typeof data === "string" && data.trim()) return data
        if (data && typeof data === "object") {
          const detail = (data as { detail?: unknown }).detail
          if (typeof detail === "string" && detail.trim()) return detail
          const message = (data as { message?: unknown }).message
          if (typeof message === "string" && message.trim()) return message
        }
      }

      if (error instanceof Error && error.message?.trim()) {
        return error.message
      }

      return fallback
    },
    [t]
  )

  const handleAddNews = useCallback(async () => {
    if (adding) return
    setAdding(true)
    setAddError(null)
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
      void refreshNews()
      if (imageInputRef.current) imageInputRef.current.value = ""
    } catch (error) {
      setAddError(resolveCreateError(error))
    } finally {
      setAdding(false)
    }
  }, [adding, imageFile, imagePreview, language, newsData, refreshNews, resolveCreateError])

  const handleCloseDialog = useCallback(() => {
    setAddOpen(false)
    setNewsData(initialNews)
    setAddError(null)
    setImageFile(null)
    if (imagePreview) {
      URL.revokeObjectURL(imagePreview)
      setImagePreview(null)
    }
    if (imageInputRef.current) imageInputRef.current.value = ""
  }, [imagePreview])

  const loadMore = useCallback(async () => {
    if (hasNextPage) {
      await fetchNextPage()
    }
  }, [hasNextPage, fetchNextPage])

  const loadingMore = isFetchingNextPage

  return (
    <Layout>
      <PageFadeIn>
        <div className="w-screen min-h-screen bg-[color:var(--page-bg)] text-[color:var(--page-text)] py-8 sm:py-10">
          <div className="px-2 md:px-4">
            <div
              data-fade
              style={fadeDelayStyle("80ms")}
              className="mb-8 flex flex-wrap items-center gap-4 sm:gap-5"
            >
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[color:color-mix(in_srgb,var(--glass-bg)_70%,var(--nav-link)_30%)] text-[color:var(--nav-link)] shadow-[0_6px_20px_color-mix(in_srgb,var(--nav-link)_24%,transparent)] transition-transform duration-200 hover:scale-105 dark:bg-[color:color-mix(in_srgb,var(--glass-bg)_65%,var(--nav-link)_35%)] dark:shadow-[0_8px_24px_color-mix(in_srgb,var(--nav-link)_28%,transparent)] backdrop-blur-sm [-webkit-backdrop-filter:blur(12px)]">
                <ArticleIcon className="text-[2rem]" />
              </div>
              <h1 className="text-[clamp(1.6rem,5vw,2.75rem)] font-bold tracking-tight text-[color:var(--page-text)]">
                {t("news:pageTitle")}
              </h1>
            </div>

            {user?.role === "admin" && (
              <div data-fade style={fadeDelayStyle("140ms")} className="mb-6 flex justify-start">
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
              style={fadeDelayStyle("200ms")}
              className="grid gap-6 grid-cols-[repeat(auto-fill,minmax(340px,1fr))]"
            >
              {isInitialLoading
                ? Array.from({ length: skeletonCount }).map((_, index) => (
                  <div key={`news-skeleton-${index}`} className="flex h-full w-full">
                    <NewsCardSkeleton />
                  </div>
                ))
                : newsList.map((news) => (
                  <div key={news.id} className="flex h-full w-full">
                    <NewsCard
                      {...news}
                      image_url={news.image_url ?? undefined}
                      onChange={() => {
                        void refreshNews()
                      }}
                    />
                  </div>
                ))}

              {showEmptyState && (
                <div className="col-span-full mt-16 flex w-full justify-start">
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

            {/* Load more */}
            {hasNextPage && (
              <div className="mt-8 mb-8 flex justify-center">
                <Button
                  variant="outline"
                  size="lg"
                  onClick={loadMore}
                  disabled={loadingMore}
                  className="px-6"
                >
                  {loadingMore
                    ? t("common:statuses.loading")
                    : t("common:buttons.loadMore", { defaultValue: "Load more" })}
                </Button>
              </div>
            )}

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
                {addError ? (
                  <Alert severity="error" variant="outlined">
                    {addError}
                  </Alert>
                ) : null}

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
        </div>
      </PageFadeIn>
    </Layout>
  )
}

export default News
