import { useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"

import {
  Button,
  Chip,
  Alert,
  CircularProgress,
  SectionSubtitle,
  AccordionSection,
  SessionItem,
} from "@/components/settings"

import type { SettingsSectionProps } from "@/pages/settings/types"
import type { ActiveSessionOut } from "@/api/generated"

interface SessionsSectionProps extends SettingsSectionProps {
  sessions: ActiveSessionOut[]
  sortedSessions: ActiveSessionOut[]
  sessionsFetching: boolean
  sessionsErrorMessage: string | null
  revokeAllPending: boolean
  revokeSessionPending: boolean
  onRevokeSession: (sessionId: string) => Promise<void>
  onRevokeAllSessions: () => Promise<void>
  formatSessionTimestamp: (value: string) => string
}

export function SessionsSection({
  sessions,
  sortedSessions,
  sessionsFetching,
  sessionsErrorMessage,
  revokeAllPending,
  revokeSessionPending,
  onRevokeSession,
  onRevokeAllSessions,
  formatSessionTimestamp,
}: SessionsSectionProps) {
  const { t } = useTranslation(["settings"])

  return (
    <AccordionSection
      title={t("settings:sessions.title")}
      subtitle={t("settings:sessions.subtitle")}
    >
      <div className="flex flex-col gap-3">
        <div className="flex flex-col items-start gap-2.5 sm:flex-row sm:items-center sm:justify-between">
          <Button
            variant="outline"
            color="error"
            disabled={revokeAllPending}
            onClick={() => void onRevokeAllSessions()}
            leadingIcon={
              revokeAllPending ? <CircularProgress size={18} color="inherit" /> : undefined
            }
          >
            {t("settings:sessions.revokeAll")}
          </Button>
          <SectionSubtitle className="text-sm">
            {t("settings:sessions.revokeAllHint")}
          </SectionSubtitle>
        </div>

        {sessions.length === 0 && sessionsFetching ? (
          <div className="mt-3 flex flex-row items-center gap-2.5">
            <CircularProgress size={18} />
            <p className="text-sm font-semibold text-text-primary">
              {t("settings:sessions.loading")}
            </p>
          </div>
        ) : sessionsErrorMessage ? (
          <Alert severity="error" className="mt-3">
            {sessionsErrorMessage}
          </Alert>
        ) : sessions.length === 0 ? (
          <SectionSubtitle className="mt-3 text-sm">{t("settings:sessions.empty")}</SectionSubtitle>
        ) : (
          <div className="flex flex-col gap-3 mt-3">
            {sortedSessions.map((session) => {
              const isRevoked = Boolean(session.revoked_at)
              const lastSeen = session.last_seen_at ?? session.created_at
              const timelineSource = session.revoked_at ?? lastSeen
              const timeline = t("settings:sessions.lastSeen.value", {
                value: formatSessionTimestamp(timelineSource),
              })
              const ipLabel = session.ip_address
                ? t("settings:sessions.ipAddress", { ip: session.ip_address })
                : t("settings:sessions.ipUnknown")
              const meta = [ipLabel, timeline]
              if (isRevoked) meta.push(t("settings:sessions.status.revoked"))
              const details = meta.join(" • ")
              const statusLabel = session.is_current
                ? t("settings:sessions.status.current")
                : isRevoked
                  ? t("settings:sessions.status.revoked")
                  : t("settings:sessions.status.active")
              const disableRevoke = session.is_current || isRevoked || revokeSessionPending

              return (
                <SessionItem key={session.id} data-revoked={isRevoked ? "true" : undefined}>
                  <div className="min-w-0">
                    <p
                      className={cn(
                        "text-sm wrap-break-word transition-colors",
                        session.is_current ? "font-semibold" : "font-medium",
                        isRevoked
                          ? "text-text-primary/(--opacity-strong)"
                          : "text-(--text-secondary)"
                      )}
                    >
                      {session.user_agent || t("settings:sessions.unknownDevice")}
                    </p>
                    <p
                      className={cn(
                        "text-xs transition-colors",
                        isRevoked ? "italic text-session-revoked" : "text-session-meta"
                      )}
                    >
                      {details}
                    </p>
                  </div>
                  <div className="flex flex-row flex-wrap items-center justify-start gap-2 gap-y-1.5 sm:justify-end">
                    <Chip
                      key={isRevoked ? "revoked" : "active"}
                      data-testid={`session-status-${session.id}`}
                      label={statusLabel}
                      color={session.is_current ? "primary" : "default"}
                      className={cn("font-semibold", isRevoked && "opacity-hover")}
                    />
                    {!session.is_current && !isRevoked && (
                      <Button
                        data-testid={`session-revoke-${session.id}`}
                        size="sm"
                        variant="ghost"
                        color="error"
                        disabled={disableRevoke}
                        onClick={() => void onRevokeSession(session.id)}
                      >
                        {t("settings:sessions.revoke")}
                      </Button>
                    )}
                  </div>
                </SessionItem>
              )
            })}
          </div>
        )}
      </div>
    </AccordionSection>
  )
}
