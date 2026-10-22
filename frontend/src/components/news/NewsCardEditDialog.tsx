import { FC, useState, useEffect, useRef, type FormEvent, type ReactNode } from "react"
import { Camera as PhotoCamera } from "lucide-react"
import { useTranslation } from "react-i18next"
import { useForm, Controller } from "react-hook-form"
import { valibotResolver } from "@hookform/resolvers/valibot"
import api from "@/api/client"
import { logError } from "@/app/logger"
import {
  captureActiveTelemetryContext,
  type CapturedTelemetryContext,
} from "@/utils/telemetryContext"
import { Button } from "@/components/ui/Button"
import { Dialog } from "@/components/ui/Dialog"
import SmartImage from "@/components/media/SmartImage"
import { newsFormSchema, type NewsFormValues } from "@/features/news/schema"
import { cn } from "@/utils/cn"

export interface NewsEditData {
  title: string
  content: string
  title_en: string
  content_en: string
  image_url: string
}

interface NewsCardEditDialogProps {
  id: string
  open: boolean
  onClose: () => void
  initialData: NewsEditData
  onSuccess?: () => void
}

const inputClass =
  "w-full rounded-xl border border-glass-border bg-input-mix px-4 py-2.5 text-input text-text-primary shadow-inner-premium transition focus:border-(--primary-main) focus-ring-premium placeholder:text-(--text-secondary)"
const textareaClass = cn(inputClass, "min-h-(--space-32) resize-y leading-relaxed")
const errorClass = "text-error-text text-xs mt-1 font-medium"

type FieldProps = {
  label: string
  htmlFor: string
  children: ReactNode
  error?: string
  required?: boolean
}

function Field({ label, htmlFor, children, error, required = false }: FieldProps) {
  return (
    <div className="space-y-2">
      <label htmlFor={htmlFor} className="text-sm font-semibold tracking-wide text-field-label">
        {label}
        {required ? <span className="ml-1 text-(--error-text)">*</span> : null}
      </label>
      {children}
      {error ? <p className={errorClass}>{error}</p> : null}
    </div>
  )
}

export const NewsCardEditDialog: FC<NewsCardEditDialogProps> = ({
  id,
  open,
  onClose,
  initialData,
  onSuccess,
}) => {
  const { t } = useTranslation(["news", "common"])
  const [imagePreview, setImagePreview] = useState<string | null>(null)
  const [imageLoading, setImageLoading] = useState(false)
  const imageInputRef = useRef<HTMLInputElement>(null)
  const [submissionError, setSubmissionError] = useState<"upload" | "save" | null>(null)
  const [discardConfirmationOpen, setDiscardConfirmationOpen] = useState(false)
  const [dialogTrapVersion, setDialogTrapVersion] = useState(0)

  const {
    register,
    handleSubmit,
    control,
    reset,
    watch,
    formState: { errors, isSubmitting, isValid, isDirty },
  } = useForm<NewsFormValues>({
    resolver: valibotResolver(newsFormSchema),
    mode: "onChange",
    shouldUnregister: false,
    defaultValues: {
      title: initialData.title,
      content: initialData.content,
      title_en: initialData.title_en,
      content_en: initialData.content_en,
      image: null,
    },
  })

  // Watch image for preview
  const imageFile = watch("image")

  // Reset form when dialog opens with new data
  useEffect(() => {
    if (open) {
      reset({
        title: initialData.title,
        content: initialData.content,
        title_en: initialData.title_en || "",
        content_en: initialData.content_en || "",
        image: null,
      })
      setImagePreview(null)
    }
  }, [open, initialData, reset])

  // Handle image preview
  useEffect(() => {
    if (imageFile instanceof File) {
      const url = URL.createObjectURL(imageFile)
      setImagePreview(url)
      return () => URL.revokeObjectURL(url)
    }
  }, [imageFile])

  const discardAndClose = () => {
    reset({
      title: initialData.title,
      content: initialData.content,
      title_en: initialData.title_en || "",
      content_en: initialData.content_en || "",
      image: null,
    })
    setImagePreview(null)
    setSubmissionError(null)
    setDiscardConfirmationOpen(false)
    onClose()
  }

  const keepEditing = () => setDiscardConfirmationOpen(false)

  const requestClose = () => {
    if (isSubmitting || imageLoading) {
      // Escape deactivates the focus trap. Remounting the same dialog keeps the
      // pending request visible and restores keyboard containment.
      setDialogTrapVersion((current) => current + 1)
      return
    }
    if (isDirty) {
      setDiscardConfirmationOpen(true)
      return
    }
    onClose()
  }

  const onSubmit = async (data: NewsFormValues, telemetryContext: CapturedTelemetryContext) => {
    setSubmissionError(null)
    try {
      let imgUrl = initialData.image_url

      if (data.image instanceof File) {
        const image = data.image
        setImageLoading(true)
        try {
          const formData = new FormData()
          formData.append("file", image)
          const res = await telemetryContext.run(() =>
            api.post<{ url: string }>(`/news/upload_image`, formData, {
              headers: { "Content-Type": "multipart/form-data" },
            })
          )
          imgUrl = res.data.url
        } catch (error) {
          setSubmissionError("upload")
          logError(error)
          return
        } finally {
          setImageLoading(false)
        }
      }

      // Cleared translations must be sent as explicit null: the backend uses
      // exclude_unset, so an omitted key would keep the stored English text.
      const payload = {
        title: data.title,
        content: data.content,
        title_en: data.title_en || null,
        content_en: data.content_en || null,
        image_url: imgUrl,
      }

      try {
        await telemetryContext.run(() => api.patch(`/news/${id}`, payload))
      } catch (error) {
        setSubmissionError("save")
        logError(error)
        return
      }
      telemetryContext.run(() => onSuccess?.())
      onClose()
    } catch (e) {
      logError(e)
    }
  }

  const handleTelemetrySubmit = (event: FormEvent<HTMLFormElement>) => {
    const telemetryContext = captureActiveTelemetryContext()
    return handleSubmit((data) => onSubmit(data, telemetryContext))(event)
  }

  // Determine which image to show: preview > existing > none
  const displayImage = imagePreview || initialData.image_url

  return (
    <Dialog
      key={`${discardConfirmationOpen ? "discard" : "edit"}-${dialogTrapVersion}`}
      open={open}
      onClose={discardConfirmationOpen ? keepEditing : requestClose}
      title={
        discardConfirmationOpen
          ? t("common:dialogs.unsavedChanges.title")
          : t("news:dialogs.edit.title")
      }
      subtitle={
        discardConfirmationOpen
          ? t("common:dialogs.unsavedChanges.description")
          : t("news:dialogs.edit.description")
      }
      size="md"
      fullScreenOnMobile
      closeLabel={t("common:buttons.close")}
      bodyClassName="space-y-4"
      footerClassName="flex-col-reverse gap-3 sm:flex-row"
      footer={
        discardConfirmationOpen ? (
          <>
            <Button variant="outline" onClick={keepEditing} className="w-full sm:w-auto">
              {t("common:buttons.keepEditing")}
            </Button>
            <Button variant="solid" onClick={discardAndClose} className="w-full sm:w-auto">
              {t("common:buttons.discardChanges")}
            </Button>
          </>
        ) : (
          <>
            <Button
              variant="outline"
              onClick={requestClose}
              disabled={isSubmitting || imageLoading}
              className="w-full sm:w-auto"
            >
              {t("common:buttons.cancel")}
            </Button>
            <Button
              form={`news-edit-form-${id}`}
              type="submit"
              disabled={!isValid || isSubmitting || imageLoading}
              loading={isSubmitting || imageLoading}
              className="w-full sm:w-auto"
            >
              {t("common:buttons.save")}
            </Button>
          </>
        )
      }
    >
      {discardConfirmationOpen ? null : (
        <form id={`news-edit-form-${id}`} className="space-y-4" onSubmit={handleTelemetrySubmit}>
          {submissionError ? (
            <p role="alert" className={errorClass}>
              {submissionError === "upload"
                ? t("news:form.errors.uploadFailed")
                : t("news:notifications.savedError")}
            </p>
          ) : null}
          <Field
            label={t("news:form.title") ?? ""}
            htmlFor={`news-edit-title-${id}`}
            required
            error={errors.title?.message}
          >
            <input
              id={`news-edit-title-${id}`}
              type="text"
              className={cn(inputClass, errors.title && "border-error-text/50")}
              disabled={isSubmitting || imageLoading}
              {...register("title")}
            />
          </Field>

          <Field
            label={t("news:form.text") ?? ""}
            htmlFor={`news-edit-content-${id}`}
            required
            error={errors.content?.message}
          >
            <textarea
              id={`news-edit-content-${id}`}
              className={cn(textareaClass, errors.content && "border-error-text/50")}
              rows={4}
              disabled={isSubmitting || imageLoading}
              {...register("content")}
            />
          </Field>

          <Field
            label={t("news:form.title_en") ?? ""}
            htmlFor={`news-edit-title-en-${id}`}
            error={errors.title_en?.message}
          >
            <input
              id={`news-edit-title-en-${id}`}
              type="text"
              className={cn(inputClass, errors.title_en && "border-error-text/50")}
              disabled={isSubmitting || imageLoading}
              {...register("title_en")}
            />
          </Field>

          <Field
            label={t("news:form.content_en") ?? ""}
            htmlFor={`news-edit-content-en-${id}`}
            error={errors.content_en?.message}
          >
            <textarea
              id={`news-edit-content-en-${id}`}
              className={cn(textareaClass, errors.content_en && "border-error-text/50")}
              rows={4}
              disabled={isSubmitting || imageLoading}
              {...register("content_en")}
            />
          </Field>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <Controller
              control={control}
              name="image"
              render={({ field: { value: _value, onChange, ...field } }) => (
                <>
                  <Button
                    type="button"
                    onClick={() => imageInputRef.current?.click()}
                    variant="outline"
                    size="sm"
                    leadingIcon={<PhotoCamera size={20} />}
                    className={cn(
                      "w-full sm:w-auto",
                      errors.image && "border-error-text/50 text-error-text"
                    )}
                    disabled={imageLoading || isSubmitting}
                  >
                    {imageLoading ? t("common:statuses.uploading") : t("news:form.changePhoto")}
                  </Button>
                  <input
                    {...field}
                    ref={(element) => {
                      imageInputRef.current = element
                      field.ref(element)
                    }}
                    type="file"
                    accept="image/*"
                    hidden
                    value=""
                    onChange={(e) => {
                      const file = e.target.files?.[0]
                      if (file) onChange(file)
                    }}
                  />
                </>
              )}
            />

            {displayImage ? (
              <SmartImage
                srcRaw={displayImage}
                alt={t("news:alt.preview")}
                className="h-20 w-full max-w-44 rounded-lg border border-white/(--opacity-subtle) object-cover shadow-surface"
              />
            ) : null}
          </div>
          {errors.image?.message ? <p className={errorClass}>{errors.image.message}</p> : null}
        </form>
      )}
    </Dialog>
  )
}
