import { useTranslation } from "react-i18next"
import { Calendar as EventNoteIcon } from "lucide-react"
import { Button } from "@/components/ui"

type EventTabKey = "active" | "archive" | "my"

type EventsEmptyStateProps = {
  tab: EventTabKey
  onTabChange: (tab: EventTabKey) => void
}

export function EventsEmptyState({ tab, onTabChange }: EventsEmptyStateProps) {
  const { t } = useTranslation(["events"])

  const hintKey =
    tab === "active"
      ? "events:states.emptyHint.active"
      : tab === "archive"
        ? "events:states.emptyHint.archive"
        : "events:states.emptyHint.my"

  return (
    <div className="col-span-full mt-12 flex w-full justify-center animate-in fade-in slide-in-from-bottom-4 duration-slow">
      <div className="flex w-full max-w-[28rem] flex-col items-center gap-5 rounded-lg border border-glass-border/(--opacity-soft) bg-(--bg-surface)/(--opacity-medium) px-8 py-14 text-center shadow-glass backdrop-blur-md">
        <div className="relative z-base flex h-16 w-16 items-center justify-center rounded-full bg-brand/(--opacity-subtle) border border-brand/(--opacity-dim) shadow-brand/(--opacity-subtle) shadow-lg">
          <EventNoteIcon className="h-8 w-8 text-brand" />
        </div>
        <div className="space-y-2">
          <p className="text-lg font-semibold text-text-primary">{t("events:states.empty")}</p>
          <p className="text-sm text-(--text-secondary)">{t(hintKey)}</p>
        </div>
        {tab !== "my" && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onTabChange(tab === "active" ? "archive" : "active")}
            className="mt-2 text-brand hover:bg-brand/(--opacity-subtle)"
          >
            {tab === "active" ? t("events:tabs.archive") : t("events:tabs.active")}
          </Button>
        )}
      </div>
    </div>
  )
}
