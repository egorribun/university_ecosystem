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
        onClick={onToggle}
        className="w-full flex items-center justify-between px-6 py-5 hover:bg-(--bg-surface)/(--opacity-dim) transition-colors"
      >
        <h2 className="text-lg font-bold tracking-tight text-(--text-primary)">
          {t("profile:titles.details")}
        </h2>
        <ExpandMoreIcon
          className={cn(
            "h-5 w-5 text-(--brand-main) transition-transform duration-300",
            isOpen && "rotate-180"
          )}
        />
      </button>

      <div
        className={cn(
          "transition-all duration-300 overflow-hidden",
          isOpen ? "max-h-[1000px] opacity-100" : "max-h-0 opacity-0"
        )}
      >
        <div className="px-3 pb-6 flex flex-col gap-1">
          <DetailRow label={t("profile:labels.institute")} value={user?.institute} />
          <Divider className="opacity-(--opacity-subtle) mx-4" />
          <DetailRow label={t("profile:labels.educationLevel")} value={user?.education_level} />
          <Divider className="opacity-(--opacity-subtle) mx-4" />
          <DetailRow
            label={
              user?.role === "teacher" ? t("profile:labels.department") : t("profile:labels.track")
            }
            value={user?.role === "teacher" ? user?.department : user?.track}
          />
          <Divider className="opacity-(--opacity-subtle) mx-4" />
          <DetailRow
            label={
              user?.role === "teacher" ? t("profile:labels.position") : t("profile:labels.program")
            }
            value={user?.role === "teacher" ? user?.position : user?.program}
          />
          <Divider className="opacity-(--opacity-subtle) mx-4" />
          <DetailRow
            label={t("profile:labels.about")}
            value={
              <span className="wrap-break-word">
                {user?.about || t("profile:placeholders.about")}
              </span>
            }
          />
        </div>
      </div>
    </SectionCard>
  )
}

export default ProfileDetails
