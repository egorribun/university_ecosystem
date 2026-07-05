import { useState, useRef, useActionState, useOptimistic, type ChangeEvent } from "react"
import { useTranslation } from "react-i18next"
import { Trash2 as DeleteIcon } from "lucide-react"
import { isAxiosError } from "axios"
import api from "@/api/client"
import { logError } from "@/app/logger"
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

  const [optimisticFiles, mutateFiles] = useOptimistic<OptimisticEventFile[], FileOptimisticAction>(
    event.files ?? [],
    applyOptimisticFileAction
  )

  const [uploadState, uploadAction, uploadPending] = useActionState<UploadState, FormData>(
    async (_prev, input) => {
      if (input.get("__upload_reset__") === "1") {
        return { status: "idle" }
      }

      const file = input.get("file")
      if (!(file instanceof File) || file.size === 0) {
        return { status: "error", error: t("events:detail.upload.errors.noFile") }
      }

      const optimisticId = `pending-${Date.now()}`
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
        await api.post(`/events/${event.id}/upload_file`, data)
        mutateFiles({ type: "remove", id: optimisticId })
        onSuccess(t("events:detail.messages.fileAdded"))
        setSelectedFile(null)
        if (fileInputRef.current) fileInputRef.current.value = ""
        await onUpdate()
        return { status: "success" }
      } catch (err) {
        logError("[EventFileManager] Upload failed:", err)
        mutateFiles({ type: "remove", id: optimisticId })

        let message = t("events:detail.messages.fileAddFailed")
        if (isAxiosError(err) && err.response?.data?.detail) {
          message = err.response.data.detail
        }
        onError(message)
        return { status: "error", error: t("events:detail.upload.errors.failed") }
      }
    },
    { status: "idle" }
  )

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const nextFile = e.target.files?.[0] || null
    setSelectedFile(nextFile)
    if (isUploadErrorState(uploadState) && !uploadPending) {
      const marker = new FormData()
      marker.append("__upload_reset__", "1")
      uploadAction(marker)
    }
  }

  const handleDeleteFile = async (fileId: string) => {
    mutateFiles({ type: "remove", id: fileId })
    try {
      await api.delete(`/events/file/${fileId}`)
      onSuccess(t("events:detail.messages.fileDeleted"))
    } catch (err) {
      logError("[EventFileManager] Delete failed:", err)
      onError(t("events:detail.messages.fileDeleteFailed"))
    } finally {
      await onUpdate()
    }
  }

  return (
    <>
      {canEdit && (
        <div>
          <form action={uploadAction} className="flex flex-wrap items-center gap-2">
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
                <div key={f.id} className="flex items-center gap-2">
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
                      onClick={() => {
                        if (!isPendingFile) {
                          void handleDeleteFile(f.id)
                        }
                      }}
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
