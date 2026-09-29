import { useId, useState, type ChangeEvent, type FormEvent } from "react"
import { useMutation } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import { useTranslation } from "react-i18next"
import { Megaphone } from "lucide-react"

import {
  announcePlatformRelease,
  isReleaseVersion,
  type ReleaseAnnouncementResult,
} from "@/api/notifications"
import { Alert, Button, SectionCard, TextField } from "@/components/settings"

type Translate = ReturnType<typeof useTranslation>["t"]

function releaseErrorMessage(error: unknown, t: Translate): string {
  if (isAxiosError(error)) {
    if (error.response?.status === 429) return t("admin:notifications.release.rateLimited")
    const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
    if (typeof detail === "string" && detail) return detail
    if (detail && typeof detail === "object") {
      const message = (detail as { message?: unknown }).message
      if (typeof message === "string" && message) return message
    }
  }
  return t("admin:notifications.release.error")
}

function releaseOutcome(result: ReleaseAnnouncementResult, t: Translate): string {
  const values = { version: result.version, count: result.created }
  if (!result.already_announced) return t("admin:notifications.release.sent", values)
  if (result.created > 0) return t("admin:notifications.release.caughtUp", values)
  return t("admin:notifications.release.alreadyAnnounced", values)
}

/** Admin form announcing a released platform version (topic system.release). */
export function ReleaseAnnouncementCard() {
  const { t } = useTranslation(["admin"])
  const headingId = useId()
  const [version, setVersion] = useState("")
  const [notesRu, setNotesRu] = useState("")
  const [notesEn, setNotesEn] = useState("")
  const [touched, setTouched] = useState(false)

  const mutation = useMutation({ mutationFn: announcePlatformRelease })

  const trimmedVersion = version.trim()
  const versionValid = isReleaseVersion(trimmedVersion)
  const showVersionError = touched && !versionValid

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setTouched(true)
    // The fields and button are disabled while a request is pending.
    if (!versionValid) return
    mutation.mutate({ version: trimmedVersion, notesRu, notesEn })
  }

  // Editing the form dismisses the previous outcome (a no-op while idle).
  const resetFeedback = () => mutation.reset()

  return (
    <SectionCard className="p-6">
      <form onSubmit={handleSubmit} aria-labelledby={headingId} noValidate>
        <h2 id={headingId} className="mb-1 text-lg font-bold tracking-tight text-text-primary">
          {t("admin:notifications.release.title")}
        </h2>
        <p className="mb-6 text-sm text-(--text-secondary)">
          {t("admin:notifications.release.description")}
        </p>

        <div className="flex flex-col gap-4">
          <TextField
            label={t("admin:notifications.release.versionLabel")}
            value={version}
            onChange={(event: ChangeEvent<HTMLInputElement>) => {
              setVersion(event.target.value)
              resetFeedback()
            }}
            onBlur={() => setTouched(true)}
            error={showVersionError}
            helperText={
              showVersionError
                ? t("admin:notifications.release.invalidVersion")
                : t("admin:notifications.release.versionHelper")
            }
            disabled={mutation.isPending}
            autoComplete="off"
            required
            className="sm:max-w-(--min-w-filter)"
          />
          <TextField
            label={t("admin:notifications.release.notesRuLabel")}
            value={notesRu}
            onChange={(event: ChangeEvent<HTMLInputElement>) => {
              setNotesRu(event.target.value)
              resetFeedback()
            }}
            multiline
            rows={3}
            maxLength={2000}
            disabled={mutation.isPending}
            fullWidth
          />
          <TextField
            label={t("admin:notifications.release.notesEnLabel")}
            value={notesEn}
            onChange={(event: ChangeEvent<HTMLInputElement>) => {
              setNotesEn(event.target.value)
              resetFeedback()
            }}
            multiline
            rows={3}
            maxLength={2000}
            disabled={mutation.isPending}
            fullWidth
          />
          <div>
            <Button
              type="submit"
              disabled={mutation.isPending}
              startIcon={<Megaphone className="h-4 w-4" aria-hidden="true" />}
            >
              {t("admin:notifications.release.submit")}
            </Button>
          </div>
        </div>

        <div aria-live="polite" className="mt-4 empty:hidden">
          {mutation.isSuccess && (
            <Alert severity={mutation.data.already_announced ? "info" : "success"}>
              {releaseOutcome(mutation.data, t)}
            </Alert>
          )}
          {mutation.isError && (
            <Alert severity="error">{releaseErrorMessage(mutation.error, t)}</Alert>
          )}
        </div>
      </form>
    </SectionCard>
  )
}
