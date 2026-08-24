import { useTranslation } from "react-i18next"
import { useNavigate } from "@tanstack/react-router"

import { useAuth } from "@/contexts/AuthContext"
import { useAvatarUpload } from "@/pages/settings/hooks/useAvatarUpload"
import { useCoverUpload } from "@/pages/settings/hooks/useCoverUpload"

import {
  Button,
  Avatar,
  SectionCard,
  SectionTitle,
  SectionSubtitle,
  AccordionSection,
} from "@/components/settings"

import type { SettingsSectionProps } from "@/pages/settings/types"

export function ProfileSection({ setSnackbar }: SettingsSectionProps) {
  const { t } = useTranslation(["settings", "common"])
  const navigate = useNavigate()
  const { user } = useAuth()

  const {
    avatarSrc,
    handleError: handleAvatarError,
    triggerPick: triggerAvatarPick,
    busy: avatarBusy,
    remove: removeAvatar,
    inputRef: avatarInputRef,
    upload: uploadAvatar,
  } = useAvatarUpload(setSnackbar)

  const {
    coverSrc,
    coverUrl,
    triggerPick: triggerCoverPick,
    busy: coverBusy,
    remove: removeCover,
    inputRef: coverInputRef,
    upload: uploadCover,
  } = useCoverUpload(setSnackbar)

  return (
    <SectionCard component="section">
      <div className="flex flex-col gap-2 mb-4">
        <SectionTitle variant="subtitle1">{t("settings:account.profile.title")}</SectionTitle>
        <SectionSubtitle variant="body2">{t("settings:account.profile.subtitle")}</SectionSubtitle>
      </div>

      <ul className="flex flex-col gap-3 list-none m-0 p-0">
        {/* Avatar Section */}
        <li className="list-none">
          <AccordionSection
            title={t("settings:media.avatar.title")}
            subtitle={t("settings:media.avatar.subtitle")}
          >
            <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center">
              <Avatar
                src={avatarSrc}
                alt={user?.full_name || "avatar"}
                className="w-20 h-20"
                imgProps={{
                  onError: handleAvatarError,
                  loading: "lazy",
                  decoding: "async",
                  referrerPolicy: "no-referrer",
                }}
              />
              <div className="flex flex-col sm:flex-row gap-2 flex-1">
                <Button
                  size="sm"
                  variant="solid"
                  onClick={triggerAvatarPick}
                  disabled={avatarBusy}
                  className="w-full sm:w-auto"
                >
                  {t("settings:media.avatar.change")}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  color="error"
                  onClick={removeAvatar}
                  disabled={avatarBusy}
                  className="w-full sm:w-auto"
                >
                  {t("settings:media.avatar.delete")}
                </Button>
              </div>
            </div>
          </AccordionSection>
        </li>

        {/* Cover Section */}
        <li className="list-none">
          <AccordionSection
            title={t("settings:media.cover.title")}
            subtitle={t("settings:media.cover.subtitle")}
          >
            <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center">
              <div
                data-testid="settings-cover-preview"
                className="h-20 w-32 rounded-xl border shrink-0"
                style={{
                  background: coverSrc
                    ? `url(${coverSrc}) center/cover no-repeat`
                    : "var(--bg-surface-hover)",
                  borderColor: "var(--glass-border-subtle)",
                }}
              />
              <div className="flex flex-col sm:flex-row gap-2 flex-1">
                <Button
                  size="sm"
                  variant="solid"
                  onClick={triggerCoverPick}
                  disabled={coverBusy}
                  className="w-full sm:w-auto"
                >
                  {t("settings:media.cover.change")}
                </Button>
                {coverUrl && (
                  <Button
                    size="sm"
                    variant="outline"
                    color="error"
                    onClick={removeCover}
                    disabled={coverBusy}
                    className="w-full sm:w-auto"
                  >
                    {t("settings:media.cover.remove")}
                  </Button>
                )}
              </div>
            </div>
          </AccordionSection>
        </li>

        {/* User Info Section */}
        <li className="list-none">
          <AccordionSection
            title={t("settings:account.profile.extra.title")}
            subtitle={t("settings:account.profile.extra.subtitle")}
          >
            <div className="flex flex-col gap-3">
              <SectionSubtitle className="text-sm">
                {t("settings:account.profile.extra.hint")}
              </SectionSubtitle>
              <Button
                size="sm"
                variant="outline"
                onClick={() => navigate({ to: "/profile", search: { edit: "1" } })}
                className="self-start"
              >
                {t("common:buttons.edit")}
              </Button>
            </div>
          </AccordionSection>
        </li>
      </ul>

      {/* Hidden File Inputs */}
      <input
        ref={avatarInputRef}
        type="file"
        accept="image/*"
        hidden
        onChange={(e) => {
          const f = e.currentTarget.files?.[0]
          if (f) {
            uploadAvatar(f)
          } else {
            return
          }
        }}
      />
      <input
        ref={coverInputRef}
        type="file"
        accept="image/*"
        hidden
        onChange={(e) => {
          const f = e.currentTarget.files?.[0]
          if (f) {
            uploadCover(f)
          } else {
            return
          }
        }}
      />
    </SectionCard>
  )
}
