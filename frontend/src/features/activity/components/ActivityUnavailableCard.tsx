import { useTranslation } from "react-i18next"

import CardShell from "./CardShell"

type ActivityUnavailableCardProps = {
  title: string
}

export function ActivityUnavailableCard({ title }: ActivityUnavailableCardProps) {
  const { t } = useTranslation(["activity"])

  return (
    <CardShell tone="neutral" aria-label={title}>
      <div className="flex min-h-24 flex-col items-center justify-center text-center">
        <p className="font-bold text-text-primary">{title}</p>
        <p className="mt-1 text-sm text-text-secondary">{t("activity:partial.feedUnavailable")}</p>
      </div>
    </CardShell>
  )
}
