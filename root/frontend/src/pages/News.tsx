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
  useId,
  type CSSProperties,
} from "react"
import { createNews, uploadNewsImage } from "@/api/news"
import ArticleIcon from "@mui/icons-material/Article"
import PhotoCamera from "@mui/icons-material/PhotoCamera"
import AddRoundedIcon from "@mui/icons-material/AddRounded"
import SmartImage from "@/components/SmartImage"
import { Button, Modal, ModalBody, ModalFooter, ModalHeader, modalFieldStyles } from "@/components/ui"
import { useAuth } from "../contexts/AuthContext"
import { useLanguage } from "../contexts/LanguageContext"
import { useTranslation } from "react-i18next"
import { useNewsFeed } from "@/hooks/useNewsFeed"
import useMediaQuery from "@/hooks/useMediaQuery"
import { cn } from "@/utils/cn"

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
  const isMobile = useMediaQuery("(max-width: 640px)")

  const addDialogTitleId = useId()
  const titleId = useId()
  const contentId = useId()
  const titleEnId = useId()
  const contentEnId = useId()
  const fileInputId = useId()

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
    [imagePreview],
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

  const handleSubmit = useCallback(
    (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault()
      void handleAddNews()
    },
    [handleAddNews],
  )

  const visibleList = useMemo(
    () => (visibleCount > 0 ? deferredList.slice(0, visibleCount) : deferredList),
    [deferredList, visibleCount],
  )

  return (
    <Layout>
      <PageFadeIn>
        <section className="w-full bg-[color:var(--page-bg)]">
          <div className="relative mx-auto w-full max-w-7xl px-4 pb-16 pt-8 sm:px-8 lg:px-16 xl:px-24">
            <div
              data-fade
              style={{ "--fade-delay": "80ms" } as CSSProperties}
              className="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="flex items-center gap-4">
                <span className="relative grid h-14 w-14 place-items-center overflow-hidden rounded-full bg-[color:color-mix(in_srgb,var(--dash-card-news-orb,#2563eb)_26%,transparent_74%)] shadow-[0_20px_45px_rgba(59,130,246,0.18)]">
                  <span className="absolute inset-0 bg-[radial-gradient(circle_at_30%_30%,rgba(255,255,255,0.35),transparent_60%)]" aria-hidden />
                  <ArticleIcon style={{ fontSize: 32, color: "var(--nav-link)" }} />
                </span>
                <div>
                  <p className="text-sm font-semibold uppercase tracking-[0.28em] text-[color:color-mix(in_srgb,var(--secondary-text,#64748b)_72%,white_28%)]">
                    {t("news:pageSubtitle", { defaultValue: t("news:pageTitle") })}
                  </p>
                  <h1 className="text-3xl font-black tracking-tight text-[color:var(--page-text)] sm:text-[clamp(2.1rem,4vw,2.75rem)]">
                    {t("news:pageTitle")}
                  </h1>
                </div>
              </div>

              {user?.role === "admin" && (
                <Button
                  size="md"
                  className="w-full sm:w-auto"
                  onClick={() => setAddOpen(true)}
                  loading={adding}
                  leadingIcon={<AddRoundedIcon fontSize="small" />}
                >
                  {t("news:actions.add")}
                </Button>
              )}
            </div>

            <div
              data-fade
              style={{ "--fade-delay": "200ms" } as CSSProperties}
              className="mt-10 grid gap-5 sm:grid-cols-2 xl:grid-cols-3"
            >
              {Array.isArray(visibleList) &&
                visibleList.map((news) => (
                  <div
                    key={news.id}
                    className="flex w-full"
                  >
                    <NewsCard
                      {...news}
                      image_url={news.image_url ?? undefined}
                      onChange={() => {
                        void refetchNews()
                      }}
                    />
                  </div>
                ))}
            </div>

            {Array.isArray(newsList) && showEmptyState && (
              <div
                data-fade
                style={{ "--fade-delay": "260ms" } as CSSProperties}
                className="mt-16 flex justify-center"
              >
                <div className="max-w-lg rounded-ue-2xl border border-[color:color-mix(in_srgb,var(--page-border,rgba(148,163,184,0.36))_65%,transparent_35%)] bg-[color:color-mix(in_srgb,var(--page-bg,#fff)_85%,white_15%)] px-10 py-12 text-center shadow-[0_25px_60px_rgba(15,23,42,0.12)]">
                  <p className="text-lg font-semibold text-[color:color-mix(in_srgb,var(--secondary-text,#64748b)_90%,white_10%)]">
                    {t("news:states.empty")}
                  </p>
                </div>
              </div>
            )}

            <Modal
              open={addOpen}
              onClose={handleCloseDialog}
              labelledBy={addDialogTitleId}
              fullScreenOnMobile={isMobile}
              size="sm"
              panelClassName={cn(isMobile ? "rounded-none" : "")}
            >
              <ModalHeader titleId={addDialogTitleId}>
                {t("news:dialogs.create.title")}
              </ModalHeader>
              <form onSubmit={handleSubmit} className="flex h-full flex-col">
                <ModalBody>
                  <div className="flex flex-col gap-4">
                    <label htmlFor={titleId} className={modalFieldStyles.label}>
                      {t("news:form.title")}
                      <input
                        id={titleId}
                        type="text"
                        maxLength={100}
                        value={newsData.title}
                        onChange={(e) => setNewsData({ ...newsData, title: e.target.value })}
                        className={modalFieldStyles.input}
                        disabled={adding}
                        required
                      />
                    </label>
                    <label htmlFor={contentId} className={modalFieldStyles.label}>
                      {t("news:form.content")}
                      <textarea
                        id={contentId}
                        maxLength={3000}
                        value={newsData.content}
                        onChange={(e) => setNewsData({ ...newsData, content: e.target.value })}
                        className={modalFieldStyles.textarea}
                        disabled={adding}
                        required
                      />
                    </label>
                    <label htmlFor={titleEnId} className={modalFieldStyles.label}>
                      {t("news:form.title_en", { defaultValue: "Title (English)" })}
                      <input
                        id={titleEnId}
                        type="text"
                        maxLength={100}
                        value={newsData.title_en}
                        onChange={(e) => setNewsData({ ...newsData, title_en: e.target.value })}
                        className={modalFieldStyles.input}
                        disabled={adding}
                      />
                    </label>
                    <label htmlFor={contentEnId} className={modalFieldStyles.label}>
                      {t("news:form.content_en", { defaultValue: "News text (English)" })}
                      <textarea
                        id={contentEnId}
                        maxLength={3000}
                        value={newsData.content_en}
                        onChange={(e) => setNewsData({ ...newsData, content_en: e.target.value })}
                        className={modalFieldStyles.textarea}
                        disabled={adding}
                      />
                    </label>
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                      <Button
                        as="label"
                        variant="outline"
                        size="md"
                        className="cursor-pointer"
                        leadingIcon={<PhotoCamera fontSize="small" />}
                        disabled={adding}
                      >
                        {imageFile ? t("common:buttons.changePhoto") : t("common:buttons.uploadPhoto")}
                        <input
                          id={fileInputId}
                          ref={imageInputRef}
                          type="file"
                          accept="image/*"
                          hidden
                          onChange={handleImageChange}
                          disabled={adding}
                        />
                      </Button>
                      {imagePreview && (
                        <SmartImage
                          srcRaw={imagePreview}
                          alt={t("news:alt.newCover")}
                          style={{
                            width: 132,
                            height: 80,
                            borderRadius: 18,
                            border: "1px solid rgba(148,163,184,0.32)",
                            boxShadow: "0 12px 32px rgba(15,23,42,0.18)",
                          }}
                        />
                      )}
                    </div>
                  </div>
                </ModalBody>
                <ModalFooter>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={handleCloseDialog}
                    disabled={adding}
                  >
                    {t("common:buttons.cancel")}
                  </Button>
                  <Button
                    type="submit"
                    loading={adding}
                    disabled={!newsData.title.trim() || !newsData.content.trim()}
                  >
                    {adding ? t("common:statuses.publishing") : t("news:actions.publish")}
                  </Button>
                </ModalFooter>
              </form>
            </Modal>
          </div>
        </section>
      </PageFadeIn>
    </Layout>
  )
}

export default News
