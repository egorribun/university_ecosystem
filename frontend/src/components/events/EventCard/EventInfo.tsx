import { Tooltip } from "@/components/ui"
import { MapPin as PlaceIcon, Calendar as EventIcon } from "lucide-react"
import { useTranslation } from "react-i18next"
import { formatLocalDateTime } from "@/utils/date"

interface EventInfoProps {
  titleId?: string
  title: string
  speaker?: string
  startsAt: string
  endsAt: string
  location: string
  description: string
}

export function EventInfo({
  titleId,
  title,
  speaker,
  startsAt,
  endsAt,
  location,
  description,
}: EventInfoProps) {
  const { t } = useTranslation(["events"])

  return (
    <>
      <h3
        id={titleId}
        className="mb-2 text-xl font-extrabold leading-tight text-text-primary sm:text-2xl"
      >
        {title}
      </h3>

      {speaker && (
        <p className="mb-2 text-body-sm font-semibold text-(--text-secondary)">
          {t("events:form.speaker")}: {speaker}
        </p>
      )}

      <div className="mb-2 flex items-center gap-2 group/date">
        <Tooltip content={t("events:form.dates")}>
          <EventIcon
            size={20}
            className="text-brand transition-transform group-hover/date:scale-110"
          />
        </Tooltip>
        <div className="text-base text-(--text-secondary)">
          <time dateTime={startsAt}>{formatLocalDateTime(startsAt)}</time>
          <span> — </span>
          <time dateTime={endsAt}>{formatLocalDateTime(endsAt)}</time>
        </div>
      </div>

      <div className="mb-2 flex items-center gap-2 group/loc">
        <Tooltip content={t("events:form.location")}>
          <PlaceIcon
            size={20}
            className="text-brand transition-transform group-hover/loc:scale-110"
          />
        </Tooltip>
        <span className="text-base text-(--text-secondary)">{location}</span>
      </div>

      <div className="my-3 h-px bg-linear-to-r from-transparent via-event-divider to-transparent" />

      <p className="mb-4 line-clamp-3 text-base text-text-primary grow-0">{description}</p>
    </>
  )
}
