import { useTranslation } from "react-i18next"
import { ChevronDown as ExpandMoreIcon } from "lucide-react"
import { SectionCard } from "@/components/settings"
import { Divider } from "@/components/settings"
import { cn } from "@/utils/cn"
import DetailRow from "./DetailRow"
import type { User } from "@/types/User"

type ProfileDetailsProps = {
  user: User | null
  isOpen: boolean
  onToggle: () => void
}

export const ProfileDetails = ({ user, isOpen, onToggle }: ProfileDetailsProps) => {
  const { t } = useTranslation(["profile"])

  return (
    <SectionCard className="p-0 border-none bg-(--bg-surface)/(--opacity-subtle) rounded-3xl overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={isOpen}
        className="mt-(--space-4) space-y-1 relative items-center justify-between px-6 py-5 hover:bg-(--bg-surface)/(--opacity-dim) transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-(--bg-surface)"
      >
        <h2 className="text-lg font-bold tracking-tight text-text-primary">
          {t("profile:sections.details")}
        </h2>
        <ExpandMoreIcon
          className={cn(
            "h-5 w-5 text-(--brand-main) transition-transform duration-base",
            isOpen && "rotate-180"
          )}
        />
      </button>

      <div
        className="grid transition-[grid-template-rows,opacity] duration-base"
        style={{
          gridTemplateRows: isOpen ? "1fr" : "0fr",
          opacity: isOpen ? 1 : 0,
        }}
      >
        <div className="overflow-hidden">
          <div className="px-3 pb-6 flex flex-col gap-1">
            <DetailRow
              label={t("profile:labels.institute")}
              value={user?.education_path?.institute}
            />
            <Divider className="opacity-subtle mx-4" />
            <DetailRow
              label={t("profile:labels.educationLevel")}
              value={user?.education_path?.education_level}
            />
            <Divider className="opacity-subtle mx-4" />
            <DetailRow
              label={
                user?.role === "teacher"
                  ? t("profile:labels.department")
                  : t("profile:labels.track")
              }
              value={
                user?.role === "teacher"
                  ? user?.profile_detail?.department
                  : user?.education_path?.track
              }
            />
            <Divider className="opacity-subtle mx-4" />
            <DetailRow
              label={
                user?.role === "teacher"
                  ? t("profile:labels.position")
                  : t("profile:labels.program")
              }
              value={
                user?.role === "teacher"
                  ? user?.profile_detail?.position
                  : user?.education_path?.program
              }
            />
            <Divider className="opacity-subtle mx-4" />
            <DetailRow
              label={t("profile:labels.about")}
              value={
                <span className="wrap-break-word">
                  {user?.profile_detail?.about || t("profile:placeholders.about")}
                </span>
              }
            />
          </div>
        </div>
      </div>
    </SectionCard>
  )
}

export default ProfileDetails
