import Layout from "../components/Layout"
import PageFadeIn from "../components/PageFadeIn"
import NewsCard from "../components/NewsCard"
import NewsCardSkeleton from "../components/NewsCardSkeleton"
import { useState, useRef, useCallback, useEffect, type ReactNode, type CSSProperties } from "react"
import { isAxiosError } from "axios"
import { createNews, uploadNewsImage } from "@/api/news"
import { Newspaper as ArticleIcon, Camera as PhotoCamera, Search as SearchIcon } from "lucide-react"
import SmartImage from "@/components/SmartImage"
import { Button } from "@/components/ui"
import { Alert, Dialog, DialogActions, DialogContent, DialogTitle } from "@/components/settings"
import { useAuth } from "../contexts/AuthContext"
import { useLanguage } from "../contexts/LanguageContext"
import { useOnlineStatus } from "@/hooks/useOnlineStatus"
import OfflineFallback from "@/components/OfflineFallback"
import { useTranslation } from "react-i18next"
import { useQueryClient } from "@tanstack/react-query"
import { useNewsListQuery } from "@/api/hooks/news"
import { resetEtagCache } from "@/api/client"
import { StorageItem } from "@/utils/storage"
import { cn } from "@/utils/cn"

const inputClass =
  "w-full rounded-xl border border-glass-border bg-surface/40 px-4 py-2.5 text-[0.98rem] text-primary-text shadow-sm focus:border-brand focus:outline-none transition placeholder:text-secondary-text/50"
const textareaClass = cn(inputClass, "min-h-[148px] resize-y leading-relaxed")

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
        className="text-sm font-semibold tracking-wide text-secondary-text/80"
      >
        {label}
        {required ? <span className="ml-1 text-red-500">*</span> : null}
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
    refetch: refetchNews,
  } = useNewsListQuery({ language })

  const isOnline = useOnlineStatus()

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

  // Persist to localStorage for E2E tests expectations and offline fallback
  useEffect(() => {
    if (newsList.length > 0) {
      const storage = new StorageItem<typeof newsList>(`news:list:${language}`)
      storage.set(newsList)
    }
  }, [newsList, language])

  const handleImageChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0]
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
        <div className="w-full min-h-screen bg-transparent text-primary-text py-8 sm:py-10">
          <div className="px-4">
            <div
              data-fade
              style={fadeDelayStyle("80ms")}
              className="mb-8 flex flex-wrap items-center gap-4 sm:gap-5"
            >
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-surface/40 border border-glass-border text-brand shadow-glass transition-transform duration-200 hover:scale-105 backdrop-blur-md">
                <ArticleIcon className="h-7 w-7" />
              </div>
              <h1 className="text-[clamp(1.6rem,5vw,2.75rem)] font-bold tracking-tight text-primary-text">
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
              className="grid gap-6 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3"
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
                <div className="col-span-full mt-12 flex w-full justify-center">
                  {!isOnline && newsList.length === 0 ? (
                    <OfflineFallback onRetry={refreshNews} />
                  ) : (
                    <div className="flex w-full max-w-md flex-col items-center gap-5 rounded-3xl border border-glass-border/30 bg-surface/40 px-8 py-14 text-center shadow-glass backdrop-blur-md">
                      <div className="flex h-16 w-16 items-center justify-center rounded-full bg-brand/10 border border-brand/20 shadow-brand/10 shadow-lg">
                        <ArticleIcon className="h-8 w-8 text-brand" />
                      </div>
                      <div className="space-y-2">
                        <p className="text-lg font-semibold text-primary-text">
                          {t("news:states.empty")}
                        </p>
                        <p className="text-sm text-secondary-text">
                          {t("news:states.checkLater", {
                            defaultValue: "Check back later for updates",
                          })}
                        </p>
                      </div>
                      {user?.role === "admin" && (
                        <Button size="lg" onClick={() => setAddOpen(true)} className="mt-2 px-6">
                          {t("news:actions.add")}
                        </Button>
                      )}
                    </div>
                  )}
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

            <Dialog open={addOpen} onClose={handleCloseDialog} maxWidth="lg" fullWidth>
              <DialogTitle>{t("news:dialogs.create.title")}</DialogTitle>
              <DialogContent className="space-y-6 pt-4">
                <form
                  className="grid grid-cols-1 md:grid-cols-2 gap-6"
                  onSubmit={(event) => {
                    event.preventDefault()
                    void handleAddNews()
                  }}
                >
                  <div className="space-y-4">
                    {addError ? <Alert severity="error">{addError}</Alert> : null}

                    <Field label={t("news:form.title") ?? ""} htmlFor="news-title" required>
                      <input
                        id="news-title"
                        ref={titleInputRef}
                        type="text"
                        value={newsData.title}
                        onChange={(event) =>
                          setNewsData({ ...newsData, title: event.target.value })
                        }
                        maxLength={100}
                        disabled={adding}
                        className={inputClass}
                      />
                    </Field>

                    <Field label={t("news:form.content") ?? ""} htmlFor="news-content" required>
                      <textarea
                        id="news-content"
                        value={newsData.content}
                        onChange={(event) =>
                          setNewsData({ ...newsData, content: event.target.value })
                        }
                        maxLength={3000}
                        disabled={adding}
                        className={textareaClass}
                        rows={6}
                      />
                    </Field>
                  </div>

                  <div className="space-y-4">
                    <Field
                      label={t("news:form.title_en", { defaultValue: "Title (English)" }) ?? ""}
                      htmlFor="news-title-en"
                    >
                      <input
                        id="news-title-en"
                        type="text"
                        value={newsData.title_en}
                        onChange={(event) =>
                          setNewsData({ ...newsData, title_en: event.target.value })
                        }
                        maxLength={100}
                        disabled={adding}
                        className={inputClass}
                      />
                    </Field>

                    <Field
                      label={
                        t("news:form.content_en", { defaultValue: "News text (English)" }) ?? ""
                      }
                      htmlFor="news-content-en"
                    >
                      <textarea
                        id="news-content-en"
                        value={newsData.content_en}
                        onChange={(event) =>
                          setNewsData({ ...newsData, content_en: event.target.value })
                        }
                        maxLength={3000}
                        disabled={adding}
                        className={textareaClass}
                        rows={6}
                      />
                    </Field>

                    <div className="space-y-3">
                      <label className="block text-sm font-semibold text-secondary-text">
                        {t("news:form.image", { defaultValue: "Cover Image" })}
                      </label>
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                        <Button
                          as="label"
                          variant="outline"
                          size="sm"
                          className="w-full sm:w-auto bg-surface/20 border-glass-border"
                          disabled={adding}
                        >
                          <div className="flex items-center gap-2">
                            <PhotoCamera className="h-4 w-4" />
                            {imageFile
                              ? t("common:buttons.changePhoto")
                              : t("common:buttons.uploadPhoto")}
                          </div>
                          <input
                            type="file"
                            accept="image/*"
                            hidden
                            ref={imageInputRef}
                            onChange={handleImageChange}
                          />
                        </Button>

                        {imagePreview ? (
                          <div className="overflow-hidden rounded-xl border border-glass-border shadow-sm">
                            <SmartImage
                              srcRaw={imagePreview}
                              alt={t("news:alt.newCover")}
                              className="h-14 w-28 object-cover"
                            />
                          </div>
                        ) : null}
                      </div>
                    </div>
                  </div>
                </form>
              </DialogContent>
              <DialogActions className="flex-col-reverse gap-3 sm:flex-row p-6">
                <Button
                  variant="ghost"
                  onClick={handleCloseDialog}
                  disabled={adding}
                  className="w-full sm:w-auto"
                >
                  {t("common:buttons.cancel")}
                </Button>
                <Button
                  variant="solid"
                  onClick={() => {
                    void handleAddNews()
                  }}
                  disabled={!newsData.title.trim() || !newsData.content.trim() || adding}
                  className="w-full sm:w-auto min-w-[120px]"
                >
                  {adding ? t("common:statuses.publishing") : t("news:actions.publish")}
                </Button>
              </DialogActions>
            </Dialog>
          </div>
        </div>
      </PageFadeIn>
    </Layout>
  )
}

export default News
