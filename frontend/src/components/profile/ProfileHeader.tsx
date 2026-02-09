import React, { useRef } from "react"
import { motion } from "framer-motion"
import { useTranslation } from "react-i18next"
import {
  Mail as EmailIcon,
  Send as TelegramIcon,
  QrCode as QrCodeIcon
} from "lucide-react"
import { QRCodeSVG } from "qrcode.react"
import { Button } from "@/components/ui"
import { SectionCard } from "@/components/settings"
import SmartImage from "@/components/SmartImage"
import { cn } from "@/utils/cn"
import type { User } from "@/types/User"
import { resolveMediaUrl, addVersionParam } from "@/utils/media"
import { AVATAR_PLACEHOLDER_URL } from "@/constants/placeholders"
import profileBg from "@/assets/background.png"

const DEFAULT_AVATAR = AVATAR_PLACEHOLDER_URL

type ProfileHeaderProps = {
  user: User | null
  avatarVersion: number
  coverVersion: number
  coverParallax: number
  coverScale: number
  avatarSize: string
  heroPaddingBottom: string
  isOnline: boolean
  statusOffset: number
  statusSize: number
  onEmailClick: (e: React.MouseEvent<HTMLButtonElement>) => void
  onTelegramClick: (e: React.MouseEvent<HTMLButtonElement>) => void
  onQrClick: () => void
  vCardData: string
  reduceMotion: boolean
  emailButtonRef: React.RefObject<HTMLButtonElement | null>
  telegramButtonRef: React.RefObject<HTMLButtonElement | null>
}

export const ProfileHeader = ({
  user,
  avatarVersion,
  coverVersion,
  coverParallax,
  coverScale,
  avatarSize,
  heroPaddingBottom,
  isOnline,
  statusOffset,
  statusSize,
  onEmailClick,
  onTelegramClick,
  onQrClick,
  vCardData,
  reduceMotion,
  emailButtonRef,
  telegramButtonRef,
}: ProfileHeaderProps) => {
  const { t } = useTranslation(["profile"])

  return (
    <div className="flex flex-col gap-4 sm:gap-5 md:gap-6 lg:gap-8 items-stretch">
      {/* Hero Card with Cover and Avatar */}
      <div
        className="relative rounded-xl sm:rounded-2xl md:rounded-3xl overflow-hidden min-h-[280px] xs:min-h-[300px] sm:min-h-[320px] md:min-h-[340px] lg:min-h-[360px] xl:min-h-[380px] flex items-end justify-center bg-surface-alt/10 shadow-glass border border-glass-border/20"
        style={{ paddingBottom: heroPaddingBottom }}
      >
        {/* Cover Image with Parallax */}
        <div
          className={cn(
            "absolute inset-0 bg-center bg-cover",
            !reduceMotion && "transition-transform duration-1200 cubic-bezier-[0.33,1,0.68,1]"
          )}
          style={{
            transform: `translateY(${coverParallax}px) scale(${coverScale})`,
            filter: "saturate(1) contrast(1.02) brightness(0.98)",
          }}
        >
          <SmartImage
            srcRaw={user?.cover_url ?? undefined}
            fallback={profileBg}
            cacheV={coverVersion}
            className="w-full h-full object-cover"
          />
        </div>

        {/* Dark Matte Overlay */}
        <div className="absolute inset-0 bg-linear-to-b from-transparent via-transparent to-[color-mix(in_srgb,var(--bg-page)_85%,transparent)] dark:to-[color-mix(in_srgb,var(--bg-page)_92%,transparent)] from-35%" />

        {/* Avatar Container */}
        <div
          className="absolute left-1/2 top-8 xs:top-10 sm:top-12 md:top-14 -translate-x-1/2 flex items-center justify-center p-0.5 sm:p-1"
          style={{ width: avatarSize, height: avatarSize }}
        >
          <div className="relative w-full h-full rounded-full bg-white/10 overflow-hidden shadow-2xl ring-2 ring-white/50 backdrop-blur-sm">
            <SmartImage
              srcRaw={user?.avatar_url ?? undefined}
              fallback={DEFAULT_AVATAR}
              cacheV={avatarVersion}
              alt={user?.full_name ?? undefined}
              className="w-full h-full rounded-full object-cover"
            />
          </div>

          {/* Online Status Indicator */}
          {isOnline && (
            <div
              className="absolute z-deep rounded-full bg-(--success-bg) shadow-glow-green pointer-events-none"
              style={{
                right: `${statusOffset}px`,
                bottom: `${statusOffset}px`,
                width: `${statusSize}px`,
                height: `${statusSize}px`,
              }}
            >
              <div className="absolute inset-0 animate-online-pulse rounded-full bg-(--success-bg)/60" />
            </div>
          )}
        </div>

        {/* User Headline Info */}
        <div className="absolute left-0 right-0 top-0 bottom-0 pointer-events-none flex items-end justify-center">
          <div className="w-full px-6 pb-6 text-center">
            <h1 className="text-2xl sm:text-3xl md:text-4xl font-bold tracking-tight text-white drop-shadow-lg">
              {user?.full_name}
            </h1>
            <p className="text-sm sm:text-base text-white/80 font-medium drop-shadow-md mt-1">
              {user?.status || t("profile:placeholders.status")}
            </p>
          </div>
        </div>
      </div>

      {/* Stats Panel */}
      <div className="grid grid-cols-2 gap-4 rounded-xl sm:rounded-2xl md:rounded-3xl p-4 bg-(--bg-surface)/30 border border-(--glass-border)/10 backdrop-blur-sm shadow-glass">
        <div className="flex flex-col items-center justify-center py-2 text-center border-r border-(--glass-border)/10">
          <span className="text-xl font-bold text-(--brand-main)">
            {user?.course || "—"}
          </span>
          <span className="text-[10px] font-bold uppercase tracking-widest text-(--secondary-text) opacity-60">
            {t("profile:labels.course")}
          </span>
        </div>
        <div className="flex flex-col items-center justify-center py-2 text-center">
          <div className="relative z-2">
            <div className="flex items-center gap-1">
              <span className="text-xl font-bold text-(--brand-main)">
                {user?.record_book_number || "—"}
              </span>
            </div>
          </div>
          <span className="text-[10px] font-bold uppercase tracking-widest text-(--secondary-text) opacity-60">
            {t("profile:labels.recordBook")}
          </span>
        </div>
      </div>

      {/* Contact Actions */}
      <div className="flex flex-col gap-3">
        <Button
          variant="ghost"
          leadingIcon={<EmailIcon className="shrink-0" />}
          onClick={onEmailClick}
          ref={emailButtonRef}
          className="justify-start h-12 rounded-xl bg-(--bg-surface)/20 border border-(--glass-border)/10 hover:bg-(--bg-surface)/40 hover:border-(--brand-main)/30"
        >
          <span className="truncate text-sm font-medium">
            {user?.email || t("profile:placeholders.email")}
          </span>
        </Button>
        {!!user?.telegram && (
          <Button
            variant="ghost"
            leadingIcon={<TelegramIcon className="shrink-0" />}
            onClick={onTelegramClick}
            ref={telegramButtonRef}
            className="justify-start h-12 rounded-xl bg-(--bg-surface)/20 border border-(--glass-border)/10 hover:bg-(--bg-surface)/40 hover:border-(--brand-main)/30"
          >
            <span className="truncate text-sm font-medium">
              {user?.telegram || t("profile:placeholders.telegram")}
            </span>
          </Button>
        )}
      </div>

      {/* vCard QR Section */}
      <SectionCard className="p-5 flex flex-col gap-4">
        <h2 className="text-xs font-bold uppercase tracking-wider text-(--secondary-text) opacity-60 flex items-center gap-2">
          <QrCodeIcon className="h-3.5 w-3.5" />
          {t("profile:labels.vcard")}
        </h2>
        <div className="flex items-center gap-4">
          <button
            type="button"
            className="qr-minimal h-20 w-20 rounded-xl bg-white p-2 shadow-sm cursor-pointer hover:scale-105 transition-transform flex items-center justify-center border-none"
            onClick={onQrClick}
            aria-label={t("profile:labels.viewQR")}
          >
            <QRCodeSVG value={vCardData} size={64} />
          </button>
          <div className="flex flex-col gap-2">
            <p className="text-xs text-secondary-text leading-relaxed">
              {t("profile:tooltips.scanToSave")}
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={onQrClick}
              className="h-8 rounded-lg text-[10px] font-bold uppercase tracking-wider"
            >
              {t("profile:buttons.viewQR")}
            </Button>
          </div>
        </div>
      </SectionCard>
    </div>
  )
}

export default ProfileHeader
