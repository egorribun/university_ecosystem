import {
  startTransition,
  useState,
  useRef,
  useActionState,
  useOptimistic,
  type ChangeEvent,
} from "react"
import { useTranslation } from "react-i18next"
import { Trash2 as DeleteIcon } from "lucide-react"
import { isAxiosError } from "axios"
import api from "@/api/client"
import { logError } from "@/app/logger"
import {
  captureActiveTelemetryContext,
  type CapturedTelemetryContext,
} from "@/utils/telemetryContext"
import { Button } from "@/components/ui"
import { resolveMediaUrl } from "@/utils/media"

import type { Event } from "@/types/Event"
import {
  applyOptimisticFileAction,
  isUploadErrorState,
  type FileOptimisticAction,
  type OptimisticEventFile,
  type UploadState,
} from "./helpers"

/** Keep upload state construction and input cleanup deterministic and directly testable. */
export function createUploadSuccessState(): UploadState {
  return { status: "success" }
}

export function createUploadErrorState(error: string): UploadState {
  return { status: "error", error }
}

export function resetFileInputValue(input: HTMLInputElement | null): void {
  if (input) input.value = ""
}

/** Keep the optimistic remove action's discriminant and identifier coupled. */
export function createRemoveFileAction(fileId: string): FileOptimisticAction {
  return { type: "remove", id: fileId }
}

/** Normalize browser file-list edge cases without relying on optional DOM fields. */
export function getSelectedFile(files: FileList | null | undefined): File | null {
  return files?.[0] ?? null
}

/** Decide whether selecting a new file should clear a settled upload error. */
export function shouldResetUploadError(uploadState: UploadState, uploadPending: boolean): boolean {
  return isUploadErrorState(uploadState) && !uploadPending
}

/** Stable translation contract for the upload submit button. */
export function getUploadSubmitLabelKey(uploadPending: boolean): string {
  return uploadPending ? "events:detail.upload.submit.pending" : "events:detail.upload.submit.label"
}

/** Serialize the pending state for stable DOM/test automation contracts. */
export function getPendingFileAttribute(isPendingFile: boolean): "true" | "false" {
  return isPendingFile ? "true" : "false"
}

interface EventFileManagerProps {
  event: Event
  canEdit: boolean
  onUpdate: () => Promise<void>
  onError: (msg: string) => void
  onSuccess: (msg: string) => void
}

export function EventFileManager({
  event,
  canEdit,
  onUpdate,
  onError,
  onSuccess,
}: EventFileManagerProps) {
  const { t } = useTranslation(["events", "common"])
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const uploadTelemetryContextRef = useRef<CapturedTelemetryContext | null>(null)

  const [optimisticFiles, mutateFiles] = useOptimistic<OptimisticEventFile[], FileOptimisticAction>(
    event.files ?? [],
    applyOptimisticFileAction
  )

  const [uploadState, uploadAction, uploadPending] = useActionState<UploadState, FormData>(
    async (_prev, input) => {
      const telemetryContext = uploadTelemetryContextRef.current ?? captureActiveTelemetryContext()
      uploadTelemetryContextRef.current = null
      if (input.get("__upload_reset__") === "1") {
        return { status: "idle" }
      }

      const file = input.get("file")
      if (!(file instanceof File) || file.size === 0) {
        return { status: "error", error: t("events:detail.upload.errors.noFile") }
      }

      const optimisticId = `optimistic-${Date.now()}`
      mutateFiles({
        type: "add",
        file: {
          id: optimisticId,
          event_id: event.id,
          description: file.name,
          file_url: "",
          pending: true,
        },
      })

      try {
        const data = new FormData()
        data.append("file", file)
        await telemetryContext.run(() => api.post(`/events/${event.id}/upload_file`, data))
        mutateFiles(createRemoveFileAction(optimisticId))
        onSuccess(t("events:detail.messages.fileAdded"))
        setSelectedFile(null)
        resetFileInputValue(fileInputRef.current)
        await telemetryContext.run(onUpdate)
        return createUploadSuccessState()
      } catch (err) {
        logError("[EventFileManager] Upload failed:", err)
        mutateFiles(createRemoveFileAction(optimisticId))

        let message = t("events:detail.messages.fileAddFailed")
        if (isAxiosError(err) && err.response?.data?.detail) {
          message = err.response.data.detail
        }
        onError(message)
        return createUploadErrorState(t("events:detail.upload.errors.failed"))
      }
    },
    { status: "idle" }
  )

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const nextFile = getSelectedFile(e.target.files)
    setSelectedFile(nextFile)
    if (shouldResetUploadError(uploadState, uploadPending)) {
      const marker = new FormData()
      marker.append("__upload_reset__", "1")
      startTransition(() => uploadAction(marker))
    }
  }

  const handleUploadSubmit = () => {
    uploadTelemetryContextRef.current = captureActiveTelemetryContext()
  }

  const handleDeleteFile = (fileId: string) => {
    const telemetryContext = captureActiveTelemetryContext()
    // useOptimistic updates must be scheduled in a transition when they are
    // initiated by an event handler (rather than a form action). Keeping the
    // async operation inside that transition preserves the optimistic row
    // until the server response settles and avoids React warnings.
    startTransition(async () => {
      mutateFiles(createRemoveFileAction(fileId))
      try {
        await telemetryContext.run(() => api.delete(`/events/file/${fileId}`))
        onSuccess(t("events:detail.messages.fileDeleted"))
      } catch (err) {
        logError("[EventFileManager] Delete failed:", err)
        onError(t("events:detail.messages.fileDeleteFailed"))
      } finally {
        await telemetryContext.run(onUpdate)
      }
    })
  }

  return (
    <>
      {canEdit && (
        <div>
          <form
            action={uploadAction}
            onSubmit={handleUploadSubmit}
            data-upload-state={uploadState.status}
            className="flex flex-wrap items-center gap-2"
          >
            <Button variant="solid" as="label" disabled={uploadPending}>
              {t("events:detail.sections.files.pickFile")}
              <input
                type="file"
                name="file"
                hidden
                required
                ref={fileInputRef}
                onChange={handleFileChange}
                disabled={uploadPending}
              />
            </Button>
            <Button variant="outline" type="submit" disabled={!selectedFile || uploadPending}>
              {uploadPending
                ? t("events:detail.upload.submit.pending")
                : t("events:detail.upload.submit.label")}
            </Button>
            {selectedFile && (
              <span
                className="ml-2 max-w-(--w-label-sm) truncate text-xs text-text-secondary"
                title={selectedFile.name}
              >
                {selectedFile.name}
              </span>
            )}
          </form>
          {isUploadErrorState(uploadState) && (
            <p className="mt-2 text-xs text-error-text">{uploadState.error}</p>
          )}
        </div>
      )}

      {optimisticFiles.length > 0 ? (
        <div>
          <h3
            id="event-files-heading"
            className="mb-2 text-(--fs-base) font-semibold text-text-primary"
          >
            {t("events:detail.sections.files.title")}
          </h3>
          <div className="space-y-2">
            {optimisticFiles.map((f) => {
              const isPendingFile = f.pending === true || f.id.toString().startsWith("pending-")
              const fallbackName = f.file_url.split("/").pop() || f.file_url
              const fileLabel = f.description || fallbackName
              return (
                <div
                  key={f.id}
                  data-file-id={f.id}
                  data-file-url={f.file_url}
                  data-file-pending={getPendingFileAttribute(isPendingFile)}
                  className="flex items-center gap-2"
                >
                  {isPendingFile ? (
                    <span className="flex-1 text-sm text-(--text-secondary)">
                      {f.description || t("events:detail.sections.files.pending")}
                    </span>
                  ) : (
                    <a
                      href={resolveMediaUrl(f.file_url) || "#"}
                      target="_blank"
                      rel="noopener noreferrer"
                      download
                      title={fileLabel}
                      aria-label={t("events:detail.sections.files.downloadAria", {
                        label: fileLabel,
                      })}
                      className="flex-1 text-sm font-medium text-(--primary-main) underline transition-colors hover:text-(--primary-dark)"
                    >
                      {fileLabel}
                    </a>
                  )}
                  {canEdit && (
                    <button
                      type="button"
                      aria-label={t("events:detail.sections.files.deleteAria")}
                      disabled={isPendingFile}
                      className="rounded-full p-1 text-error-text transition-colors hover:bg-error-bg/(--opacity-subtle) disabled:opacity-medium"
                      onClick={() => void handleDeleteFile(f.id)}
                    >
                      <DeleteIcon size={16} />
                    </button>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      ) : (
        <p className="text-sm text-(--text-secondary)">{t("events:detail.sections.files.empty")}</p>
      )}
    </>
  )
}
