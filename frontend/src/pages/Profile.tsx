import { useAuth } from "@/contexts/AuthContext"
import React, { useEffect, useMemo, useState, useRef, useCallback } from "react"
import { useLocation, useNavigate } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"
import api from "@/api/client"
import type { User } from "@/types/User"
import profileBg from "@/assets/background.png"
import guuLogo from "@/assets/guu_logo.png"
import PageFadeIn from "@/components/PageFadeIn"
import Layout from "@/components/Layout"
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Snackbar,
} from "@/components/settings"
import { motion, useReducedMotion } from "framer-motion"

import { useNowPlaying } from "@/hooks/useNowPlaying"
import { addVersionParam, resolveMediaUrl } from "@/utils/media"
import { useTranslation } from "react-i18next"
import { QRCodeSVG } from "qrcode.react"
import { ChevronDown as ExpandMoreIcon, ExternalLink as OpenInNewIcon } from "lucide-react"

import {
  NowPlayingCard,
  ProfileHeader,
  ProfileDetails,
  AchievementsSection,
  ProfileEditor,
  ProfileSkeleton,
  parseAchievements,
  buildVCardString,
  calculateAvatarSize,
  calculateHeroLayout,
  calculateStatusIndicator,
  type AchievementItem,
  type SnackbarKey,
  type SnackbarState,
} from "@/components/profile"

const isTest = typeof import.meta !== "undefined" && import.meta.env.MODE === "test"

export default function Profile() {
  const { user, loading, setUser } = useAuth()
  const [snackbar, setSnackbar] = useState<SnackbarState | null>(null)
  const [avatarVersion, setAvatarVersion] = useState(Date.now())
  const [coverVersion, setCoverVersion] = useState(Date.now())
  const reduceMotion =
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  const isWideScreen =
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(min-width: 1400px)").matches
  const isMobile =
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(max-width: 600px)").matches
  const reduced = useReducedMotion()
  const { t } = useTranslation(["profile", "common"])
  const [qrOpen, setQrOpen] = useState(false)
  const [detailsOpen, setDetailsOpen] = useState(true)
  const [achievementOpen, setAchievementOpen] = useState<AchievementItem | null>(null)
  const [emailMenuAnchor, setEmailMenuAnchor] = useState<HTMLElement | null>(null)
  const [telegramMenuAnchor, setTelegramMenuAnchor] = useState<HTMLElement | null>(null)
  const emailButtonRef = useRef<HTMLButtonElement | null>(null)
  const telegramButtonRef = useRef<HTMLButtonElement | null>(null)
  const queryClient = useQueryClient()
  const spotifyConnected = Boolean(user?.spotify_connected || user?.spotify_is_connected)
  const nowPlayingQuery = useNowPlaying(spotifyConnected)
  const nowPlaying = nowPlayingQuery.data ?? null
  const showNowPlaying = Boolean(
    spotifyConnected &&
    nowPlaying &&
    (nowPlaying.track_id || nowPlaying.track_name || nowPlaying.artists.length > 0)
  )
  const navigate = useNavigate()

  const [edit, setEdit] = useState(false)
  const [fullName, setFullName] = useState(user?.full_name || "")
  const [email, setEmail] = useState(user?.email || "")
  const [about, setAbout] = useState(user?.about || "")
  const [recordBookNumber, setRecordBookNumber] = useState(user?.record_book_number || "")
  const [status, setStatus] = useState(user?.status || "")
  const [institute, setInstitute] = useState(user?.institute || "")
  const [course, setCourse] = useState(user?.course || "")
  const [educationLevel, setEducationLevel] = useState(user?.education_level || "")
  const [track, setTrack] = useState(user?.track || "")
  const [program, setProgram] = useState(user?.program || "")
  const [telegram, setTelegram] = useState(user?.telegram || "")
  const [achievements, setAchievements] = useState(user?.achievements || "")
  const [department, setDepartment] = useState(user?.department || "")
  const [position, setPosition] = useState(user?.position || "")
  const [saving, setSaving] = useState(false)

  const initEditFields = useCallback(() => {
    setFullName(user?.full_name || "")
    setEmail(user?.email || "")
    setAbout(user?.about || "")
    setRecordBookNumber(user?.record_book_number || "")
    setStatus(user?.status || "")
    setInstitute(user?.institute || "")
    setCourse(user?.course || "")
    setEducationLevel(user?.education_level || "")
    setTrack(user?.track || "")
    setProgram(user?.program || "")
    setTelegram(user?.telegram || "")
    setAchievements(user?.achievements || "")
    setDepartment(user?.department || "")
    setPosition(user?.position || "")
  }, [user])

  useEffect(() => {
    if (user && !edit) {
      initEditFields()
    }
  }, [user, edit, initEditFields])

  if (loading) return <ProfileSkeleton />

  const isOnline = Boolean(
    (user as { is_online?: boolean; online?: boolean } | null)?.is_online ??
    (user as { is_online?: boolean; online?: boolean } | null)?.online ??
    true
  )
  const avatarPx = calculateAvatarSize(isMobile, isWideScreen)
  const { heroPaddingBottom } = calculateHeroLayout(avatarPx, isMobile)
  const { size: statusSize, offset: statusOffset } = calculateStatusIndicator(avatarPx)

  const vCardData = user ? buildVCardString(user) : ""
  const achievementsList = parseAchievements(user?.achievements)

  const handleSave = async () => {
    setSaving(true)
    try {
      const response = await api.put<User>("/users/me", {
        full_name: fullName,
        email,
        about,
        record_book_number: recordBookNumber,
        status,
        institute,
        course,
        education_level: educationLevel,
        track,
        program,
        telegram,
        achievements,
        department,
        position,
      })
      setUser(response.data)
      setEdit(false)
      navigate("/profile", { replace: true })
      setSnackbar({ key: "profileUpdated", severity: "success" })
      setAvatarVersion(Date.now())
      setCoverVersion(Date.now())
    } catch (error: unknown) {
      let messageKey: SnackbarKey | undefined = "error"
      let messageText: string | undefined

      if (error && typeof error === "object" && "response" in error) {
        const axiosError = error as {
          response: { data: { detail?: string | Array<{ msg?: string; message?: string }> } }
        }
        const detail = axiosError.response?.data?.detail

        if (detail) {
          if (typeof detail === "string") {
            messageKey = undefined
            messageText = detail
          } else if (Array.isArray(detail)) {
            messageKey = undefined
            messageText = detail
              .map((validationError) => validationError.msg || validationError.message)
              .filter(Boolean)
              .join("; ")
          }
        }
      }
      setSnackbar({ key: messageKey, message: messageText, severity: "error" })
    } finally {
      setSaving(false)
    }
  }

  const handleCancel = () => {
    setEdit(false)
    navigate("/profile", { replace: true })
  }

  const snackbarMessage = snackbar?.key
    ? t(`profile:snackbar.${snackbar.key}`)
    : snackbar?.message || ""

  return (
    <Layout className="bg-transparent!">
      <div className="fixed inset-0 z-hide pointer-events-none overflow-hidden" aria-hidden>
        <div
          className="absolute inset-0 bg-repeat bg-size-[clamp(180px,22vw,360px)] opacity-40 mix-blend-soft-light dark:opacity-20 translate-z-0"
          style={{ backgroundImage: `url(${profileBg})` }}
        />
      </div>

      <PageFadeIn>
        <motion.div
          initial={isTest ? false : { opacity: reduceMotion ? 1 : 0.96, y: reduceMotion ? 0 : 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={isTest ? { duration: 0 } : { type: "spring", stiffness: 460, damping: 34 }}
        >
          <section
            className="profile-page relative min-h-screen flex flex-col py-12 sm:py-16 md:py-20 lg:py-24 px-3 sm:px-4 md:px-6 lg:px-8"
            data-testid="profile-root"
            aria-label={t("profile:aria.page")}
          >
            <div className="max-w-full sm:max-w-[98%] md:max-w-[96%] lg:max-w-[95%] xl:max-w-[1400px] mx-auto w-full relative z-base">
              <motion.div
                className="px-4 sm:px-6 md:px-8 lg:px-10 xl:px-12 py-8 sm:py-10 md:py-12 lg:py-14 rounded-xl sm:rounded-2xl md:rounded-3xl relative overflow-hidden bg-primary-subtle-bg/10 shadow-glass border border-glass-border-subtle/20 backdrop-blur-md"
                initial={isTest ? false : { opacity: reduced ? 1 : 0.98, y: reduced ? 0 : 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={
                  isTest ? { duration: 0 } : { type: "spring", stiffness: 520, damping: 34 }
                }
              >
                <div className="grid grid-cols-1 lg:grid-cols-[minmax(280px,380px)_minmax(0,1fr)] gap-x-8 gap-y-8 items-start">
                  {/* Left Column */}
                  <div className="flex flex-col gap-6 items-stretch">
                    <ProfileHeader
                      user={user}
                      avatarVersion={avatarVersion}
                      coverVersion={coverVersion}
                      coverParallax={0}
                      coverScale={1}
                      avatarSize={`${avatarPx}px`}
                      heroPaddingBottom={heroPaddingBottom}
                      isOnline={isOnline}
                      statusOffset={statusOffset}
                      statusSize={statusSize}
                      onEmailClick={() => setSnackbar({ key: "copied", severity: "success" })}
                      onTelegramClick={() => setSnackbar({ key: "copied", severity: "success" })}
                      onQrClick={() => setQrOpen(true)}
                      vCardData={vCardData}
                      reduceMotion={reduceMotion}
                      emailButtonRef={emailButtonRef}
                      telegramButtonRef={telegramButtonRef}
                    />

                    {showNowPlaying && <NowPlayingCard data={nowPlaying!} />}
                  </div>

                  {/* Right Column */}
                  <div className="flex flex-col gap-6 min-w-0">
                    {edit ? (
                      <ProfileEditor
                        user={user}
                        fullName={fullName}
                        setFullName={setFullName}
                        email={email}
                        setEmail={setEmail}
                        telegram={telegram}
                        setTelegram={setTelegram}
                        about={about}
                        setAbout={setAbout}
                        recordBookNumber={recordBookNumber}
                        setRecordBookNumber={setRecordBookNumber}
                        status={status}
                        setStatus={setStatus}
                        institute={institute}
                        setInstitute={setInstitute}
                        course={course}
                        setCourse={setCourse}
                        educationLevel={educationLevel}
                        setEducationLevel={setEducationLevel}
                        track={track}
                        setTrack={setTrack}
                        program={program}
                        setProgram={setProgram}
                        achievements={achievements}
                        setAchievements={setAchievements}
                        department={department}
                        setDepartment={setDepartment}
                        position={position}
                        setPosition={setPosition}
                        saving={saving}
                        onSave={handleSave}
                        onCancel={handleCancel}
                      />
                    ) : (
                      <>
                        <ProfileDetails
                          user={user}
                          isOpen={detailsOpen}
                          onToggle={() => setDetailsOpen(!detailsOpen)}
                        />
                        <AchievementsSection
                          achievements={achievementsList}
                          onAchievementClick={(achievement) => setAchievementOpen(achievement)}
                        />
                        <div className="mt-4 flex justify-end">
                          <Button variant="outline" onClick={() => setEdit(true)}>
                            {t("profile:buttons.edit")}
                          </Button>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              </motion.div>
            </div>
          </section>
        </motion.div>
      </PageFadeIn>

      {/* QR Code Dialog */}
      <Dialog open={qrOpen} onClose={() => setQrOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle className="text-center">{t("profile:dialog.qr.title")}</DialogTitle>
        <DialogContent className="flex flex-col items-center justify-center gap-3 min-h-[320px]">
          <div className="bg-white p-4 rounded-2xl border border-glass-border shadow-glass">
            <QRCodeSVG value={vCardData} size={300} level="H" includeMargin />
          </div>
          <p className="text-xs text-secondary-text text-center mt-2 opacity-80">
            {t("profile:dialog.qr.hint")}
          </p>
        </DialogContent>
        <DialogActions className="justify-center">
          <Button variant="solid" onClick={() => setQrOpen(false)}>
            {t("common:buttons.done")}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Achievement Dialog */}
      <Dialog
        open={!!achievementOpen}
        onClose={() => setAchievementOpen(null)}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>{achievementOpen?.name}</DialogTitle>
        <DialogContent className="grid gap-4 py-4">
          {achievementOpen?.issuer && (
            <div className="flex flex-col gap-0.5">
              <span className="text-[10px] font-bold uppercase tracking-wider text-brand opacity-70">
                {t("profile:fields.organizer")}
              </span>
              <p className="text-primary-text font-medium">{achievementOpen.issuer}</p>
            </div>
          )}
          {achievementOpen?.url && (
            <Button
              as="a"
              href={achievementOpen.url}
              target="_blank"
              rel="noreferrer"
              variant="outline"
              fullWidth
            >
              {t("profile:dialog.achievement.openLink")}
            </Button>
          )}
        </DialogContent>
        <DialogActions>
          <Button variant="ghost" onClick={() => setAchievementOpen(null)}>
            {t("profile:dialog.achievement.close")}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar open={!!snackbar} autoHideDuration={2600} onClose={() => setSnackbar(null)}>
        <Alert onClose={() => setSnackbar(null)} severity={snackbar?.severity || "info"}>
          {snackbarMessage}
        </Alert>
      </Snackbar>
    </Layout>
  )
}
