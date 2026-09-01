import { useAuth } from "@/contexts/AuthContext"
import { useEffect, useId, useState, useRef, useCallback } from "react"
import { useNavigate, useSearch } from "@tanstack/react-router"
import "@/styles/tokens/profile.css"
import api from "@/api/client"
import type { User } from "@/types/User"
import profileBg from "@/assets/background.jpg"
import PageFadeIn from "@/components/motion/PageFadeIn"
import Layout from "@/components/Layout"
import { SEO } from "@/components/ui/SEO"
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Snackbar,
} from "@/components/settings"
import { m } from "framer-motion"
import { breakpoints } from "@/theme/tokens"
import useMediaQuery from "@/hooks/useMediaQuery"

import { useNowPlaying } from "@/hooks/useNowPlaying"
import { useTranslation } from "react-i18next"
import { QRCodeSVG } from "qrcode.react"

import {
  NowPlayingCard,
  ProfileHeader,
  ProfileDetails,
  AchievementsSection,
  ProfileEditor,
  ProfileSkeleton,
  ProfileBackdrop,
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
  // Wave 175 SW4 — 3× top-level synchronous matchMedia calls (pre-W175 inline
  // typeof-window guards) replaced with useMediaQuery hook. Benefits:
  // (a) reactive — re-renders on viewport change / system preference change
  //   (previously fixed at first render);
  // (b) consistent SSR-safety (hook handles typeof window guard internally);
  // (c) eliminates 3× repeated typeof-window/matchMedia boilerplate.
  const reduceMotion = useMediaQuery("(prefers-reduced-motion: reduce)")
  const isWideScreen = useMediaQuery(`(min-width: ${breakpoints.wide})`)
  const isMobile = useMediaQuery(`(max-width: ${breakpoints.mobile})`)
  // Wave 184 SW5 (Path D) — narrow breakpoint for ProfileBackdrop orb scaling
  // (mirrors W181 SW2 MessengerBackdrop convention). Sub-content-breakpoint
  // viewports (~< 900px) get scaled-down orbs to avoid overflow + keep
  // visual weight balanced for the smaller stage.
  const isNarrow = useMediaQuery(`(max-width: ${breakpoints.content})`)
  const { t } = useTranslation(["profile", "common"])
  const [qrOpen, setQrOpen] = useState(false)
  const [detailsOpen, setDetailsOpen] = useState(true)
  const [achievementOpen, setAchievementOpen] = useState<AchievementItem | null>(null)
  // Wave 175 SW5 — stable IDs for Dialog aria-labelledby/aria-describedby
  // wiring (shared Dialog now accepts ariaLabelledBy + ariaDescribedBy props;
  // DialogTitle + DialogContent accept matching id prop).
  const qrTitleId = useId()
  const qrDescId = useId()
  const achievementTitleId = useId()
  const achievementDescId = useId()
  const emailButtonRef = useRef<HTMLButtonElement | null>(null)
  const telegramButtonRef = useRef<HTMLButtonElement | null>(null)
  const spotifyConnected = Boolean(user?.spotify_connected || user?.spotify_is_connected)
  const nowPlayingQuery = useNowPlaying(spotifyConnected)
  const nowPlaying = nowPlayingQuery.data ?? null
  const showNowPlaying = Boolean(
    spotifyConnected &&
    nowPlaying &&
    (nowPlaying.track_id || nowPlaying.track_name || nowPlaying.artists.length > 0)
  )
  const navigate = useNavigate()
  const search = useSearch({ strict: false }) as { edit?: string }
  const shouldEditFromSearch = search.edit === "1"

  const [edit, setEdit] = useState(shouldEditFromSearch)
  const [fullName, setFullName] = useState(user?.full_name || "")
  const [email, setEmail] = useState(user?.email || "")
  const [about, setAbout] = useState(user?.profile_detail?.about || "")
  const [recordBookNumber, setRecordBookNumber] = useState(
    user?.education_path?.record_book_number || ""
  )
  const [status, setStatus] = useState(user?.profile_detail?.status || "")
  const [institute, setInstitute] = useState(user?.education_path?.institute || "")
  const [course, setCourse] = useState(user?.education_path?.course || "")
  const [educationLevel, setEducationLevel] = useState(user?.education_path?.education_level || "")
  const [track, setTrack] = useState(user?.education_path?.track || "")
  const [program, setProgram] = useState(user?.education_path?.program || "")
  const [telegram, setTelegram] = useState(user?.profile_detail?.telegram || "")
  const [achievements, setAchievements] = useState(user?.profile_detail?.achievements || "")
  const [department, setDepartment] = useState(user?.profile_detail?.department || "")
  const [position, setPosition] = useState(user?.profile_detail?.position || "")
  const [saving, setSaving] = useState(false)
  const initializedEditorUserIdRef = useRef(user?.id ?? null)

  const initEditFields = useCallback(() => {
    setFullName(user?.full_name || "")
    setEmail(user?.email || "")
    setAbout(user?.profile_detail?.about || "")
    setRecordBookNumber(user?.education_path?.record_book_number || "")
    setStatus(user?.profile_detail?.status || "")
    setInstitute(user?.education_path?.institute || "")
    setCourse(user?.education_path?.course || "")
    setEducationLevel(user?.education_path?.education_level || "")
    setTrack(user?.education_path?.track || "")
    setProgram(user?.education_path?.program || "")
    setTelegram(user?.profile_detail?.telegram || "")
    setAchievements(user?.profile_detail?.achievements || "")
    setDepartment(user?.profile_detail?.department || "")
    setPosition(user?.profile_detail?.position || "")
  }, [user])

  useEffect(() => {
    if (!user) {
      initializedEditorUserIdRef.current = null
      return
    }

    // A profile deep-link can enter edit mode before authentication finishes.
    // Populate the editor when that user first arrives, while preserving any
    // in-progress edits during background refreshes for the same account.
    if (!edit || initializedEditorUserIdRef.current !== user.id) {
      initEditFields()
      initializedEditorUserIdRef.current = user.id
    }
  }, [user, edit, initEditFields])

  useEffect(() => {
    if (shouldEditFromSearch) setEdit(true)
  }, [shouldEditFromSearch])

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
  const achievementsList = parseAchievements(user?.profile_detail?.achievements)

  const handleSave = async () => {
    setSaving(true)
    try {
      const response = await api.put<User>("/users/me", {
        full_name: fullName,
        profile_detail: {
          about,
          status,
          telegram,
          achievements,
          department,
          position,
        },
        education_path: {
          record_book_number: recordBookNumber,
          institute,
          course,
          education_level: educationLevel,
          track,
          program,
        },
      })
      setUser(response.data)
      setEdit(false)
      navigate({ to: "/profile", replace: true })
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
    navigate({ to: "/profile", replace: true })
  }

  const snackbarMessage = snackbar?.key
    ? t(`profile:snackbar.${snackbar.key}`)
    : snackbar?.message || ""

  return (
    <Layout className="bg-transparent!">
      <SEO title={t("profile:pageTitle")} />
      <div className="fixed inset-0 z-hide pointer-events-none overflow-hidden" aria-hidden>
        <div
          className="absolute inset-0 bg-repeat mix-blend-soft-light translate-z-0"
          style={{
            backgroundImage: `url(${profileBg})`,
            backgroundSize: "clamp(var(--size-pattern-min), 22vw, var(--size-pattern-max))",
            opacity: "var(--opacity-medium)",
          }}
        />
      </div>

      <PageFadeIn>
        <m.div
          initial={isTest ? false : { opacity: "var(--opacity-strong)", y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={isTest ? { duration: 0 } : { type: "spring", stiffness: 460, damping: 34 }}
        >
          {/* Wave 184 SW5 (Path D) — profile-theme scope wrapper enables
              tokens/profile.css (rose/pink/amber palette + matte cards +
              skeleton) inside this subtree. ProfileBackdrop mounts inside
              the section's `relative` positioning context so its
              `absolute inset-0` orbs span the full Profile viewport. */}
          <section
            className="profile-theme profile-page relative min-h-screen flex flex-col py-12 sm:py-16 md:py-20 lg:py-24 px-3 sm:px-4 md:px-6 lg:px-8"
            data-testid="profile-root"
            aria-label={t("profile:aria.page")}
          >
            <ProfileBackdrop
              isNarrow={isNarrow}
              isMobile={isMobile}
              prefersReducedMotion={reduceMotion}
            />
            <div className="container-fluid-responsive">
              <m.div
                className="px-4 sm:px-6 md:px-8 lg:px-10 xl:px-12 py-8 sm:py-10 md:py-12 lg:py-14 rounded-sm sm:rounded-md md:rounded-lg relative overflow-hidden bg-primary-subtle-bg/(--opacity-subtle) shadow-glass border border-glass-border-subtle/(--opacity-dim) backdrop-blur-md"
                initial={isTest ? false : { opacity: "var(--opacity-strong)", y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={
                  isTest ? { duration: 0 } : { type: "spring", stiffness: 520, damping: 34 }
                }
              >
                <div className="grid grid-cols-1 lg:grid-cols-[minmax(var(--min-w-sidebar),var(--w-sidebar-sm))_minmax(0,1fr)] gap-x-8 gap-y-8 items-start">
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
              </m.div>
            </div>
          </section>
        </m.div>
      </PageFadeIn>

      {/* QR Code Dialog */}
      <Dialog
        open={qrOpen}
        onClose={() => setQrOpen(false)}
        maxWidth="xs"
        fullWidth
        ariaLabelledBy={qrTitleId}
        ariaDescribedBy={qrDescId}
      >
        <DialogTitle id={qrTitleId} className="text-center">
          {t("profile:dialog.qr.title")}
        </DialogTitle>
        <DialogContent
          id={qrDescId}
          className="flex flex-col items-center justify-center gap-3 min-h-(--h-dialog-min)"
        >
          <div className="w-full md:w-80 lg:w-96 flex flex-col border-r border-msg-border h-full relative z-deep bg-msg-sidebar">
            {/* Wave 175 SW5 — QR is decorative (vCard meaning conveyed by
                dialog title "Share contact" + hint below); aria-hidden
                prevents screen readers from announcing "graphic" with no
                useful content (per W120 polish-v2 svg-img-alt gotcha). */}
            <QRCodeSVG value={vCardData} size={300} level="H" includeMargin aria-hidden="true" />
          </div>
          <p className="text-xs text-(--text-secondary) text-center mt-2 opacity-hover">
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
        ariaLabelledBy={achievementTitleId}
        ariaDescribedBy={achievementDescId}
      >
        <DialogTitle id={achievementTitleId}>{achievementOpen?.name}</DialogTitle>
        <DialogContent id={achievementDescId} className="grid gap-4 py-4">
          {achievementOpen?.issuer && (
            <div className="flex flex-col gap-0.5">
              <span className="text-label-xs font-bold uppercase tracking-wider text-brand opacity-strong">
                {t("profile:fields.organizer")}
              </span>
              <p className="text-text-primary font-medium">{achievementOpen.issuer}</p>
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
