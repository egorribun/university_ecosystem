/**
 * EventDetailBody — structured sections: About, Info, Files.
 * Reuses existing EventAboutEditor and EventFileManager.
 */

import type { Event } from "@/types/Event"
import { EventAboutEditor } from "./EventAboutEditor"
import { EventFileManager } from "./EventFileManager"

interface EventDetailBodyProps {
  event: Event
  language: "en" | "ru"
  isAdmin: boolean
  onRefresh: () => Promise<void>
  onError: (msg: string) => void
  onSuccess: (msg: string) => void
}

export function EventDetailBody({
  event,
  language,
  isAdmin,
  onRefresh,
  onError,
  onSuccess,
}: EventDetailBodyProps) {
  return (
    <div className="space-y-8">
      {/* About section */}
      <section aria-labelledby="event-about-heading" style={{ scrollMarginTop: "5rem" }}>
        <EventAboutEditor
          event={event}
          language={language}
          canEdit={isAdmin}
          onUpdate={onRefresh}
          onError={onError}
          onSuccess={onSuccess}
        />
      </section>

      {/* Divider */}
      <div className="h-px bg-(--glass-border)" aria-hidden="true" />

      {/* Files section */}
      <section aria-labelledby="event-files-heading" style={{ scrollMarginTop: "5rem" }}>
        <EventFileManager
          event={event}
          canEdit={isAdmin}
          onUpdate={onRefresh}
          onError={onError}
          onSuccess={onSuccess}
        />
      </section>
    </div>
  )
}
