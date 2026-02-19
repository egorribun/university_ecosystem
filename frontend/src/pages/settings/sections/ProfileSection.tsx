import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router-dom"

import { useAuth } from "../../../contexts/AuthContext"
import { useAvatarUpload } from "../hooks/useAvatarUpload"
import { useCoverUpload } from "../hooks/useCoverUpload"

import {
  Button,
  Avatar,
  SectionCard,
  SectionTitle,
  SectionSubtitle,
  AccordionSection,
} from "../../../components/settings"

import type { SettingsSectionProps } from "../types"

export function ProfileSection({ setSnackbar }: SettingsSectionProps) {
  const { t } = useTranslation(["settings", "common"])
  const navigate = useNavigate()
  const { user } = useAuth()

  const avatar = useAvatarUpload(setSnackbar)
  const cover = useCoverUpload(setSnackbar)

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
                src={avatar.avatarSrc}
                alt={user?.full_name || "avatar"}
                className="w-20 h-20"
                imgProps={{
                  onError: avatar.handleError,
                  loading: "lazy",
                  decoding: "async",
                  referrerPolicy: "no-referrer",
                }}
              />
              <div className="flex flex-col sm:flex-row gap-2 flex-1">
                <Button
                  size="sm"
                  variant="solid"
                  onClick={avatar.triggerPick}
                  disabled={avatar.busy}
                  className="w-full sm:w-auto"
                >
                  {t("settings:media.avatar.change")}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  color="error"
                  onClick={avatar.remove}
                  disabled={avatar.busy}
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
                  background: cover.coverSrc
                    ? `url(${cover.coverSrc}) center/cover no-repeat`
                    : "var(--bg-surface-hover)",
                  borderColor: "var(--glass-border-subtle)",
                }}
              />
              <div className="flex flex-col sm:flex-row gap-2 flex-1">
                <Button
                  size="sm"
                  variant="solid"
                  onClick={cover.triggerPick}
                  disabled={cover.busy}
                  className="w-full sm:w-auto"
                >
                  {t("settings:media.cover.change")}
                </Button>
                {cover.coverUrl && (
                  <Button
                    size="sm"
                    variant="outline"
                    color="error"
                    onClick={cover.remove}
                    disabled={cover.busy}
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
                onClick={() => navigate({ pathname: "/profile", search: "?edit=1" })}
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
        ref={avatar.inputRef}
        type="file"
        accept="image/*"
        hidden
        onChange={(e) => {
          const f = e.currentTarget.files?.[0]
          if (f) avatar.upload(f)
        }}
      />
      <input
        ref={cover.inputRef}
        type="file"
        accept="image/*"
        hidden
        onChange={(e) => {
          const f = e.currentTarget.files?.[0]
          if (f) cover.upload(f)
        }}
      />
    </SectionCard>
  )
}
