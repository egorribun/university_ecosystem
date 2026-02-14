import { useTranslation } from "react-i18next"

import { Button, Chip, SectionTitle } from "../../../components/settings"
import type { SettingsSectionProps } from "../types"

const SpotifyLogo = ({ className }: { className?: string }) => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" className={className}>
    <path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.508 17.302c-.216.354-.675.464-1.03.248-2.863-1.748-6.463-2.144-10.707-1.177-.404.092-.814-.16-.906-.565-.092-.404.16-.814.565-.906 4.646-1.063 8.625-.613 11.83 1.342.354.215.465.674.248 1.058zm1.467-3.258c-.272.443-.847.584-1.29.312-3.277-2.015-8.272-2.597-12.146-1.422-.497.151-1.025-.13-1.176-.627-.151-.497.13-1.025.627-1.176 4.43-1.344 9.932-.693 13.673 1.606.443.272.584.847.312 1.307zm.126-3.395C15.222 8.243 8.818 8.03 5.072 9.168c-.596.18-1.23-.153-1.41-.749-.18-.596.153-1.23.749-1.41 4.29-1.302 11.37-1.055 15.86 1.61.536.318.713 1.008.395 1.543-.318.536-1.008.713-1.543.395z" />
  </svg>
)

interface SpotifySectionProps extends SettingsSectionProps {
  connected: boolean
  displayName: string
  onConnect: () => Promise<void>
  onDisconnect: () => Promise<void>
}

export function SpotifySection({
  connected,
  displayName,
  onConnect,
  onDisconnect,
}: SpotifySectionProps) {
  const { t } = useTranslation(["settings"])

  return (
    <div className="flex w-full flex-col gap-6 sm:gap-7 xl:max-w-[min(100%,820px)]">
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-2">
          <SpotifyLogo className="rounded-full" />
          <SectionTitle variant="subtitle1" className="text-lg">
            {t("settings:integrations.spotify.title")}
          </SectionTitle>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <Chip
            label={
              connected
                ? t("settings:integrations.spotify.status.connected")
                : t("settings:integrations.spotify.status.disconnected")
            }
            color={connected ? "success" : "default"}
          />
          {connected && !!displayName && <Chip label={displayName} />}
        </div>
        {!connected ? (
          <Button variant="contained" onClick={onConnect} className="self-start">
            {t("settings:integrations.spotify.connect")}
          </Button>
        ) : (
          <Button variant="outlined" color="error" onClick={onDisconnect} className="self-start">
            {t("settings:integrations.spotify.disconnect")}
          </Button>
        )}
      </div>
    </div>
  )
}
