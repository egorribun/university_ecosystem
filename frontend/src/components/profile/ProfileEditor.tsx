import { useTranslation } from "react-i18next"
import type { User } from "@/types/User"

type ProfileEditorProps = {
  user: User | null
  fullName: string
  setFullName: (val: string) => void
  email: string
  setEmail: (val: string) => void
  telegram: string
  setTelegram: (val: string) => void
  about: string
  setAbout: (val: string) => void
  recordBookNumber: string
  setRecordBookNumber: (val: string) => void
  status: string
  setStatus: (val: string) => void
  institute: string
  setInstitute: (val: string) => void
  course: string
  setCourse: (val: string) => void
  educationLevel: string
  setEducationLevel: (val: string) => void
  track: string
  setTrack: (val: string) => void
  program: string
  setProgram: (val: string) => void
  achievements: string
  setAchievements: (val: string) => void
  department: string
  setDepartment: (val: string) => void
  position: string
  setPosition: (val: string) => void
  saving: boolean
  onSave: () => void
  onCancel: () => void
}

export const ProfileEditor = ({
  user,
  fullName,
  setFullName,
  email,
  setEmail,
  telegram,
  setTelegram,
  about,
  setAbout,
  recordBookNumber,
  setRecordBookNumber,
  status,
  setStatus,
  institute,
  setInstitute,
  course,
  setCourse,
  educationLevel,
  setEducationLevel,
  track,
  setTrack,
  program,
  setProgram,
  achievements,
  setAchievements,
  department,
  setDepartment,
  position,
  setPosition,
  saving,
  onSave,
  onCancel,
}: ProfileEditorProps) => {
  const { t } = useTranslation(["profile"])

  return (
    <div className="profile-card profile-panel profile-panel--primary profile-panel--editor profile-edit w-full rounded-xl sm:rounded-2xl p-4 sm:p-6 md:p-8 lg:p-10">
      <div className="flex flex-col gap-4 sm:gap-5">
        {/* Name Field */}
        <div className="flex flex-col gap-1.5 sm:gap-2">
          <label className="text-xs sm:text-sm font-bold text-page-foreground">
            {t("profile:form.name")}
          </label>
          <input
            type="text"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            maxLength={120}
            className="w-full px-3 sm:px-4 py-2 sm:py-3 text-sm sm:text-base rounded-lg sm:rounded-xl border border-(--glass-border) bg-(--bg-surface) text-(--primary-text) placeholder:text-(--secondary-text)/50 focus:outline-none focus:ring-2 focus:ring-(--brand-main) focus:border-transparent transition-all duration-200"
          />
        </div>

        {/* Email Field */}
        <div className="flex flex-col gap-1.5 sm:gap-2">
          <label className="text-xs sm:text-sm font-bold text-page-foreground">
            {t("profile:form.email")}
          </label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full px-3 sm:px-4 py-2 sm:py-3 text-sm sm:text-base rounded-lg sm:rounded-xl border border-glass-border bg-surface text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-(--brand-main) focus:border-transparent transition-all duration-200"
          />
        </div>

        {/* Telegram Field */}
        <div className="flex flex-col gap-1.5 sm:gap-2">
          <label className="text-xs sm:text-sm font-bold text-page-foreground">
            {t("profile:form.telegram")}
          </label>
          <input
            type="text"
            value={telegram}
            onChange={(e) => setTelegram(e.target.value)}
            className="w-full px-3 sm:px-4 py-2 sm:py-3 text-sm sm:text-base rounded-lg sm:rounded-xl border border-glass-border bg-surface text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-(--brand-main) focus:border-transparent transition-all duration-200"
          />
          <p className="text-[10px] xs:text-xs text-hint">
            {t("profile:form.telegramHint")}
          </p>
        </div>

        {/* Teacher Fields */}
        {user?.role === "teacher" && (
          <>
            <div className="flex flex-col gap-1.5 sm:gap-2">
              <label className="text-xs sm:text-sm font-bold text-page-foreground">
                {t("profile:form.department")}
              </label>
              <input
                type="text"
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
                className="w-full px-3 sm:px-4 py-2 sm:py-3 text-sm sm:text-base rounded-lg sm:rounded-xl border border-glass-border bg-surface text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-(--brand-main) focus:border-transparent transition-all duration-200"
              />
            </div>
            <div className="flex flex-col gap-1.5 sm:gap-2">
              <label className="text-xs sm:text-sm font-bold text-page-foreground">
                {t("profile:form.position")}
              </label>
              <input
                type="text"
                value={position}
                onChange={(e) => setPosition(e.target.value)}
                className="w-full px-3 sm:px-4 py-2 sm:py-3 text-sm sm:text-base rounded-lg sm:rounded-xl border border-glass-border bg-surface text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-(--brand-main) focus:border-transparent transition-all duration-200"
              />
            </div>
          </>
        )}

        {/* Student Fields */}
        {user?.role === "student" && (
          <>
            <div className="flex flex-col gap-1.5 sm:gap-2">
              <label className="text-xs sm:text-sm font-bold text-page-foreground">
                {t("profile:form.about")}
              </label>
              <textarea
                value={about}
                onChange={(e) => setAbout(e.target.value)}
                rows={3}
                className="w-full px-3 sm:px-4 py-2 sm:py-3 text-sm sm:text-base rounded-lg sm:rounded-xl border border-glass-border bg-surface text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-(--brand-main) focus:border-transparent transition-all duration-200 resize-y min-h-[70px] sm:min-h-[80px]"
              />
            </div>
            <div className="flex flex-col gap-1.5 sm:gap-2">
              <label className="text-xs sm:text-sm font-bold text-page-foreground">
                {t("profile:form.recordBookNumber")}
              </label>
              <input
                type="text"
                value={recordBookNumber}
                onChange={(e) => setRecordBookNumber(e.target.value)}
                className="w-full px-3 sm:px-4 py-2 sm:py-3 text-sm sm:text-base rounded-lg sm:rounded-xl border border-glass-border bg-surface text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-(--brand-main) focus:border-transparent transition-all duration-200"
              />
            </div>
            <div className="flex flex-col gap-1.5 sm:gap-2">
              <label className="text-xs sm:text-sm font-bold text-page-foreground">
                {t("profile:form.status")}
              </label>
              <input
                type="text"
                value={status}
                onChange={(e) => setStatus(e.target.value)}
                className="w-full px-3 sm:px-4 py-2 sm:py-3 text-sm sm:text-base rounded-lg sm:rounded-xl border border-glass-border bg-surface text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-(--brand-main) focus:border-transparent transition-all duration-200"
              />
            </div>
            <div className="flex flex-col gap-1.5 sm:gap-2">
              <label className="text-xs sm:text-sm font-bold text-page-foreground">
                {t("profile:form.institute")}
              </label>
              <input
                type="text"
                value={institute}
                onChange={(e) => setInstitute(e.target.value)}
                className="w-full px-3 sm:px-4 py-2 sm:py-3 text-sm sm:text-base rounded-lg sm:rounded-xl border border-glass-border bg-surface text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-(--brand-main) focus:border-transparent transition-all duration-200"
              />
            </div>
            <div className="flex flex-col gap-1.5 sm:gap-2">
              <label className="text-xs sm:text-sm font-bold text-page-foreground">
                {t("profile:form.course")}
              </label>
              <input
                type="text"
                value={course}
                onChange={(e) => setCourse(e.target.value)}
                className="w-full px-3 sm:px-4 py-2 sm:py-3 text-sm sm:text-base rounded-lg sm:rounded-xl border border-glass-border bg-surface text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-(--brand-main) focus:border-transparent transition-all duration-200"
              />
            </div>
            <div className="flex flex-col gap-1.5 sm:gap-2">
              <label className="text-xs sm:text-sm font-bold text-page-foreground">
                {t("profile:form.educationLevel")}
              </label>
              <input
                type="text"
                value={educationLevel}
                onChange={(e) => setEducationLevel(e.target.value)}
                className="w-full px-3 sm:px-4 py-2 sm:py-3 text-sm sm:text-base rounded-lg sm:rounded-xl border border-glass-border bg-surface text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-(--brand-main) focus:border-transparent transition-all duration-200"
              />
            </div>
            <div className="flex flex-col gap-1.5 sm:gap-2">
              <label className="text-xs sm:text-sm font-bold text-page-foreground">
                {t("profile:form.track")}
              </label>
              <input
                type="text"
                value={track}
                onChange={(e) => setTrack(e.target.value)}
                className="w-full px-3 sm:px-4 py-2 sm:py-3 text-sm sm:text-base rounded-lg sm:rounded-xl border border-glass-border bg-surface text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-(--brand-main) focus:border-transparent transition-all duration-200"
              />
            </div>
            <div className="flex flex-col gap-1.5 sm:gap-2">
              <label className="text-xs sm:text-sm font-bold text-page-foreground">
                {t("profile:form.program")}
              </label>
              <input
                type="text"
                value={program}
                onChange={(e) => setProgram(e.target.value)}
                className="w-full px-3 sm:px-4 py-2 sm:py-3 text-sm sm:text-base rounded-lg sm:rounded-xl border border-glass-border bg-surface text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-(--brand-main) focus:border-transparent transition-all duration-200"
              />
            </div>
            <div className="flex flex-col gap-1.5 sm:gap-2">
              <label className="text-xs sm:text-sm font-bold text-page-foreground">
                {t("profile:form.achievements")}
              </label>
              <textarea
                value={achievements}
                onChange={(e) => setAchievements(e.target.value)}
                rows={2}
                className="w-full px-3 sm:px-4 py-2 sm:py-3 text-sm sm:text-base rounded-lg sm:rounded-xl border border-glass-border bg-surface text-page-foreground placeholder:text-placeholder focus:outline-none focus:ring-2 focus:ring-(--brand-main) focus:border-transparent transition-all duration-200 resize-y min-h-[50px] sm:min-h-[60px]"
              />
            </div>
          </>
        )}

        {/* Action Buttons */}
        <div className="flex flex-col sm:flex-row gap-3 sm:gap-4 items-stretch sm:items-center pt-2">
          <button
            onClick={onSave}
            disabled={saving}
            className="w-full sm:w-auto py-2.5 sm:py-3 px-6 sm:px-8 rounded-lg sm:rounded-xl bg-(--nav-link) text-white font-extrabold tracking-wide text-sm sm:text-base shadow-surface hover:shadow-surface-strong transition-all duration-300 hover:-translate-y-0.5 hover:scale-[1.01] active:scale-[0.98] disabled:opacity-50 border border-(--nav-link)/20"
          >
            {saving ? t("profile:form.saving") : t("profile:form.save")}
          </button>
          <button
            onClick={onCancel}
            className="w-full sm:w-auto py-2.5 sm:py-3 px-6 sm:px-8 rounded-lg sm:rounded-xl border-2 border-glass-border bg-transparent hover:bg-surface-accent text-page-foreground font-extrabold tracking-wide text-sm sm:text-base transition-all duration-300 hover:-translate-y-0.5 hover:scale-[1.01] active:scale-[0.98]"
          >
            {t("profile:form.cancel")}
          </button>
        </div>
      </div>
    </div>
  )
}

export default ProfileEditor
