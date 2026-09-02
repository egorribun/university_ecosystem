import { useState, useCallback, useEffect, type FormEvent } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import { isAxiosError } from "axios"
import { Camera as PhotoCamera } from "lucide-react"
import { useForm, Controller } from "react-hook-form"
import { valibotResolver } from "@hookform/resolvers/valibot"
import { Dialog, DialogActions, DialogContent, DialogTitle, Alert } from "@/components/settings"
import { Button } from "@/components/ui"
import SmartImage from "@/components/media/SmartImage"
import { createNews, uploadNewsImage } from "@/api/news"
import { resetEtagCache } from "@/api/client"
import { cn } from "@/utils/cn"
import { newsFormSchema, type NewsFormValues } from "@/features/news/schema"
import {
  captureActiveTelemetryContext,
  type CapturedTelemetryContext,
} from "@/utils/telemetryContext"

const inputClass =
  "w-full rounded-md border border-glass-border bg-(--bg-surface)/(--opacity-medium) px-4 py-2.5 text-input text-text-primary shadow-sm focus:border-brand focus:outline-none transition placeholder:text-(--text-secondary)/(--opacity-medium)"
const textareaClass = cn(inputClass, "min-h-36 resize-y leading-relaxed")
const errorClass = "text-error-text text-xs mt-1 font-medium"

type FieldProps = {
  label: React.ReactNode
  htmlFor: string
  children: React.ReactNode
  error?: string
  required?: boolean
}

function Field({ label, htmlFor, children, error, required = false }: FieldProps) {
  return (
    <div className="space-y-2">
      <label
        htmlFor={htmlFor}
        className="text-sm font-semibold tracking-wide text-(--text-secondary)/(--opacity-hover)"
      >
        {label}
        {required ? <span className="ml-1 text-error-text text-sm font-bold">*</span> : null}
      </label>
      {children}
      {error ? <p className={errorClass}>{error}</p> : null}
    </div>
  )
}

interface NewsFormDialogProps {
  open: boolean
  onClose: () => void
  onSuccess?: () => void
}

export const NewsFormDialog = ({ open, onClose, onSuccess }: NewsFormDialogProps) => {
  const { t } = useTranslation(["news", "common"])
  const queryClient = useQueryClient()

  // Form setup
  const {
    register,
    handleSubmit,
    control,
    reset,
    watch,
    formState: { errors, isSubmitting, isValid },
  } = useForm<NewsFormValues>({
    resolver: valibotResolver(newsFormSchema),
    mode: "onChange",
    defaultValues: {
      title: "",
      content: "",
      title_en: "",
      content_en: "",
      image: null,
    },
  })

  // Watch image for preview
  const imageFile = watch("image")
  const [imagePreview, setImagePreview] = useState<string | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)

  // Handle image preview
  useEffect(() => {
    if (imageFile instanceof File) {
      const url = URL.createObjectURL(imageFile)
      setImagePreview(url)
      return () => URL.revokeObjectURL(url)
    } else {
      setImagePreview(null)
    }
  }, [imageFile])

  // Reset form when dialog closes/opens
  useEffect(() => {
    if (open) {
      reset()
      setSubmitError(null)
    }
  }, [open, reset])

  const resolveCreateError = useCallback(
    (error: unknown) => {
      const fallback = t("news:notifications.savedError") ?? "Failed to save the news"

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

  const onSubmit = async (data: NewsFormValues, telemetryContext: CapturedTelemetryContext) => {
    setSubmitError(null)
    try {
      let image_url = ""
      const image = data.image
      if (image) {
        const uploadedUrl = await telemetryContext.run(() => uploadNewsImage(image))
        image_url = uploadedUrl || ""
      }

      await telemetryContext.run(() =>
        createNews({
          title: data.title,
          content: data.content,
          image_url,
          title_en: data.title_en || undefined,
          content_en: data.content_en || undefined,
        })
      )

      resetEtagCache()
      void telemetryContext.run(() => queryClient.invalidateQueries({ queryKey: ["news", "list"] }))

      if (onSuccess) telemetryContext.run(onSuccess)
      onClose()
    } catch (error) {
      setSubmitError(resolveCreateError(error))
    }
  }

  const handleTelemetrySubmit = (event: FormEvent<HTMLFormElement>) => {
    const telemetryContext = captureActiveTelemetryContext()
    return handleSubmit((data) => onSubmit(data, telemetryContext))(event)
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle>{t("news:dialogs.create.title")}</DialogTitle>
      <DialogContent className="space-y-6 pt-4">
        <form
          id="news-form"
          className="grid grid-cols-1 md:grid-cols-2 gap-6"
          onSubmit={handleTelemetrySubmit}
        >
          <div className="space-y-4">
            {submitError ? <Alert severity="error">{submitError}</Alert> : null}

            <Field
              label={t("news:form.title") ?? ""}
              htmlFor="news-title"
              required
              error={errors.title?.message}
            >
              <input
                id="news-title"
                type="text"
                disabled={isSubmitting}
                className={cn(inputClass, errors.title && "border-error-text/50")}
                maxLength={100}
                {...register("title")}
              />
            </Field>

            <Field
              label={t("news:form.content") ?? ""}
              htmlFor="news-content"
              required
              error={errors.content?.message}
            >
              <textarea
                id="news-content"
                disabled={isSubmitting}
                className={cn(textareaClass, errors.content && "border-error-text/50")}
                maxLength={3000}
                rows={6}
                {...register("content")}
              />
            </Field>
          </div>

          <div className="space-y-4">
            <Field
              label={t("news:form.title_en") ?? ""}
              htmlFor="news-title-en"
              error={errors.title_en?.message}
            >
              <input
                id="news-title-en"
                type="text"
                disabled={isSubmitting}
                className={cn(inputClass, errors.title_en && "border-error-text/50")}
                maxLength={100}
                {...register("title_en")}
              />
            </Field>

            <Field
              label={t("news:form.content_en") ?? ""}
              htmlFor="news-content-en"
              error={errors.content_en?.message}
            >
              <textarea
                id="news-content-en"
                disabled={isSubmitting}
                className={cn(textareaClass, errors.content_en && "border-error-text/50")}
                maxLength={3000}
                rows={6}
                {...register("content_en")}
              />
            </Field>

            <div className="space-y-3">
              <label className="block text-sm font-semibold text-(--text-secondary)">
                {t("news:form.image")}
              </label>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                <Controller
                  control={control}
                  name="image"
                  render={({ field: { value: _value, onChange, ...field } }) => (
                    <Button
                      as="label"
                      variant="outline"
                      size="sm"
                      className={cn(
                        "w-full sm:w-auto bg-(--bg-surface)/(--opacity-dim) border-glass-border",
                        errors.image && "border-error-text/50 text-error-text"
                      )}
                      disabled={isSubmitting}
                    >
                      <div className="flex items-center gap-2">
                        <PhotoCamera className="h-4 w-4" />
                        {imageFile
                          ? t("common:buttons.changePhoto")
                          : t("common:buttons.uploadPhoto")}
                      </div>
                      <input
                        {...field}
                        type="file"
                        accept="image/*"
                        hidden
                        value="" // Important for file inputs to allow re-selecting same file
                        onChange={(e) => {
                          const file = e.target.files?.[0]
                          if (file) onChange(file)
                        }}
                      />
                    </Button>
                  )}
                />

                {imagePreview ? (
                  <div className="overflow-hidden rounded-md border border-glass-border shadow-sm">
                    <SmartImage
                      srcRaw={imagePreview}
                      alt={t("news:alt.newCover")}
                      className="h-14 w-28 object-cover"
                    />
                  </div>
                ) : null}
              </div>
              {errors.image?.message ? <p className={errorClass}>{errors.image.message}</p> : null}
            </div>
          </div>
        </form>
      </DialogContent>
      <DialogActions className="flex-col-reverse gap-3 sm:flex-row p-6">
        <Button
          variant="ghost"
          onClick={onClose}
          disabled={isSubmitting}
          className="w-full sm:w-auto"
        >
          {t("common:buttons.cancel")}
        </Button>
        <Button
          form="news-form"
          type="submit"
          variant="solid"
          disabled={!isValid || isSubmitting}
          className="w-full sm:w-auto min-w-(--min-w-btn)"
        >
          {isSubmitting ? t("common:statuses.publishing") : t("news:actions.publish")}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
