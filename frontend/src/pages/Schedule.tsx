import {
  useState,
  useEffect,
  useRef,
  useDeferredValue,
  startTransition,
  type CSSProperties,
} from "react"
import Layout from "../components/Layout"
import PageFadeIn from "../components/PageFadeIn"
import dayjs from "dayjs"
import isoWeek from "dayjs/plugin/isoWeek"
import "dayjs/locale/ru"
import "dayjs/locale/en"
import { useTranslation } from "react-i18next"
import { Button, Badge, ProgressBar, Skeleton, Card } from "@/components/ui"
import {
  Alert,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Snackbar,
} from "@/components/settings"
import {
  Clock as AccessTimeIcon,
  GraduationCap as SchoolIcon,
  MapPin as RoomIcon,
  Calendar as CalendarMonthIcon,
  Plus as AddIcon,
} from "lucide-react"
import useMediaQuery from "@/hooks/useMediaQuery"
import { useOnlineStatus } from "@/hooks/useOnlineStatus"
import OfflineFallback from "@/components/OfflineFallback"
import { cn } from "@/utils/cn"
import api from "../api/client"
import {
  type Lesson,
  type LessonParity,
  type AddLessonFields,
  buildTable,
  getTimeStr,
  getEndTimeStr,
  minutesDiff,
  parseMinutes,
} from "@/components/schedule/scheduleUtils"
import { useScheduleData } from "@/hooks/useScheduleData"
import { LessonCard } from "@/components/schedule/LessonCard"
import { WeekSelector } from "@/components/schedule/WeekSelector"
import { DayColumn } from "@/components/schedule/DayColumn"
import { ScheduleSkeleton } from "@/components/schedule/ScheduleSkeleton"

dayjs.extend(isoWeek)

const fadeDelayStyle = (value: string): CSSProperties =>
  ({ "--fade-delay": value }) as CSSProperties

export default function Schedule() {
  const { t } = useTranslation(["schedule", "common"])
  const { language } = useTranslation().i18n
  const isOnline = useOnlineStatus()

  const {
    user,
    groups,
    selectedGroup,
    setSelectedGroup,
    currentParity,
    setCurrentParity,
    schedule: filteredSchedule,
    rawSchedule: groupSchedule,
    isLoading,
    refresh,
    applyScheduleUpdate,
    weekdayBackend,
    weekdayLabels,
    weekdayShort,
    getDayLabel,
    lessonTypeOptions,
    lessonTypeLabels,
    defaultLessonType,
    getLessonTypeColor,
    toBackendLessonType,
    todayIdx,
    hasToday,
    nowTick,
    currentLesson,
    nextLesson,
    conflictedIds,
    timeLeftText,
    currentProgress,
  } = useScheduleData()

  const [snack, setSnack] = useState("")
  const [openDialog, setOpenDialog] = useState(false)
  const [dialogLesson, setDialogLesson] = useState<Lesson | null>(null)
  const [editing, setEditing] = useState(false)
  const [editLesson, setEditLesson] = useState<Lesson | null>(null)
  const [addDialogOpen, setAddDialogOpen] = useState(false)
  const [addDay, setAddDay] = useState<string>("")
  const [addFields, setAddFields] = useState<AddLessonFields>({
    subject: "",
    teacher: "",
    room: "",
    lessonType: defaultLessonType,
    startTime: "",
    endTime: "",
    parity: "both",
  })

  useEffect(() => {
    if (!defaultLessonType) return
    setAddFields((prev) => {
      if (lessonTypeOptions.some((option) => option.value === prev.lessonType)) return prev
      return { ...prev, lessonType: defaultLessonType }
    })
  }, [lessonTypeOptions, defaultLessonType])

  const editingLessonTypeOptions = lessonTypeOptions // Simplified as we have full list in hook

  const addDayLabel = addDay ? getDayLabel(addDay) : ""
  const isMobile = useMediaQuery("(max-width:1730px)")
  const tableScrollRef = useRef<HTMLDivElement | null>(null)
  const headRefs = useRef<(HTMLTableCellElement | null)[]>([])
  const dayCardRefs = useRef<(HTMLDivElement | null)[]>([])

  if (headRefs.current.length !== weekdayBackend.length)
    headRefs.current = Array(weekdayBackend.length).fill(null)
  if (dayCardRefs.current.length !== weekdayBackend.length)
    dayCardRefs.current = Array(weekdayBackend.length).fill(null)

  const tableRowsBase = buildTable(filteredSchedule, weekdayBackend)
  const tableRows = useDeferredValue(tableRowsBase)
  const [rowLimit, setRowLimit] = useState(0)

  useEffect(() => {
    setRowLimit((prev) => {
      const start = Math.min(12, tableRows.length)
      return start
    })
  }, [tableRows.length])

  useEffect(() => {
    let cancelled = false
    const chunk = 12
    const step = () => {
      if (cancelled) return
      startTransition(() => {
        setRowLimit((prev) => {
          const next = Math.min(prev + chunk, tableRows.length)
          return next
        })
      })
      if (!cancelled && rowLimit < tableRows.length) {
        if ("requestIdleCallback" in window) (window as any).requestIdleCallback(step)
        else setTimeout(step, 0)
      }
    }
    if (tableRows.length > 0 && rowLimit < tableRows.length) {
      if ("requestIdleCallback" in window) (window as any).requestIdleCallback(step)
      else setTimeout(step, 0)
    }
    return () => {
      cancelled = true
    }
  }, [tableRows, rowLimit])

  useEffect(() => {
    if (isMobile || !hasToday) return
    const container = tableScrollRef.current
    const cell = todayIdx >= 0 ? headRefs.current[todayIdx] : null
    if (container && cell) {
      const left = cell.offsetLeft - 120
      container.scrollTo({ left, behavior: "smooth" })
    }
  }, [rowLimit, isMobile, todayIdx, hasToday])

  // Helpers
  const getLessonTypeLabel = (val?: string | null) => lessonTypeLabels.get(val ?? "") ?? val ?? ""

  // Render Table
  const renderBreakChip = (rowIdx: number, colIdx: number) => {
    if (rowIdx === 0) return null
    const prev = tableRows[rowIdx - 1]?.[colIdx]
    const curr = tableRows[rowIdx]?.[colIdx]
    if (!prev || !curr) return null
    const gap = minutesDiff(prev.end_time, curr.start_time)
    if (gap <= 0) return null
    return (
      <div className="absolute left-1/2 top-[-14px] z-3 -translate-x-1/2 pointer-events-none">
        <Badge
          size="xs"
          className="chip-break font-medium bg-surface/80 border-glass-border shadow-glass text-secondary-text"
        >
          {t("schedule:break", { minutes: gap })}
        </Badge>
      </div>
    )
  }

  const renderTable = () => {
    const visibleRows = tableRows.slice(0, rowLimit)
    return (
      <div
        ref={tableScrollRef}
        className="mx-auto w-full max-w-[min(98vw,1920px)] overflow-x-auto rounded-3xl border border-glass-border bg-surface/40 text-primary-text shadow-glass backdrop-blur-md scroll-smooth"
        style={{ minHeight: 360 }}
      >
        <table className="w-full border-collapse">
          <thead className="sticky top-0 z-5">
            <tr>
              <th className="sticky left-0 z-10 w-[50px] bg-surface/60 px-4 py-4 text-center font-extrabold text-primary-text border-r border-glass-border shadow-md backdrop-blur-md">
                №
              </th>
              {weekdayBackend.map((day, idx) => {
                const label = weekdayLabels[idx] ?? day
                const isTodayCol = hasToday && idx === todayIdx
                return (
                  <th
                    key={day}
                    ref={(el: HTMLTableCellElement | null) => {
                      headRefs.current[idx] = el
                    }}
                    className={cn(
                      "relative px-4 py-4 text-center font-extrabold text-primary-text transition-all duration-300",
                      isTodayCol
                        ? "bg-brand/10 shadow-[inset_0_0_0_1px_rgba(var(--primary-main),0.2)]"
                        : "bg-surface/40",
                      "z-5 backdrop-blur-md"
                    )}
                  >
                    <div className="flex items-center justify-center gap-2">
                      <span
                        className={cn(
                          "tracking-tight",
                          isTodayCol && "text-(--nav-link)"
                        )}
                      >
                        {label}
                      </span>
                      {(user?.role === "admin" || user?.role === "teacher") && (
                        <button
                          className="ml-1 flex h-7 w-7 items-center justify-center rounded-lg border border-glass-border bg-surface/60 text-brand hover:bg-brand hover:text-white transition-colors"
                          onClick={(e) => {
                            e.stopPropagation()
                            setAddDay(day)
                            setAddDialogOpen(true)
                          }}
                        >
                          <AddIcon className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {visibleRows.length === 0 ? (
              <tr>
                <td colSpan={weekdayBackend.length + 1} className="py-12 px-6">
                  {!isOnline && groupSchedule.length === 0 ? (
                    <div className="flex justify-center">
                      <OfflineFallback onRetry={refresh} />
                    </div>
                  ) : (
                    <p className="text-center">{t("schedule:table.noLessons")}</p>
                  )}
                </td>
              </tr>
            ) : (
              visibleRows.map((row, rowIdx) => (
                <tr key={rowIdx}>
                  <td className="sticky left-0 z-10 bg-surface/60 px-4 py-3 text-center font-bold border-r border-glass-border shadow-md backdrop-blur-md">
                    {rowIdx + 1}
                  </td>
                  {row.map((lesson, colIdx) => {
                    const colIsToday = hasToday && colIdx === todayIdx
                    if (!lesson) {
                      return (
                        <td
                          key={`empty-${rowIdx}-${colIdx}`}
                          className={cn(
                            "p-3",
                            colIsToday
                              ? "bg-[color-mix(in_srgb,var(--nav-link)_3%,var(--card-bg)_97%)]"
                              : ""
                          )}
                        >
                          <div className="min-h-[148px] rounded-xl border border-dashed border-[color-mix(in_srgb,white_8%,var(--nav-link)_92%)]" />
                        </td>
                      )
                    }
                    let hasBreakBefore = false
                    if (rowIdx > 0) {
                      const prev = visibleRows[rowIdx - 1]?.[colIdx]
                      if (prev) {
                        const gap = minutesDiff(prev.end_time, lesson.start_time)
                        hasBreakBefore = gap > 0
                      }
                    }
                    const isConflict = conflictedIds.has(lesson.id)
                    return (
                      <td
                        key={lesson.id}
                        className={cn(
                          "relative overflow-visible p-3",
                          colIsToday ? "bg-brand/5" : ""
                        )}
                      >
                        {renderBreakChip(rowIdx, colIdx)}
                        <LessonCard
                          lesson={lesson}
                          isConflict={isConflict}
                          hasBreakBefore={hasBreakBefore}
                          onOpen={() => {
                            setDialogLesson(lesson)
                            setOpenDialog(true)
                          }}
                          onDelete={() => handleDeleteLesson(lesson.id)}
                          canEdit={user?.role === "admin" || user?.role === "teacher"}
                          getLessonTypeColor={getLessonTypeColor}
                          getLessonTypeLabel={getLessonTypeLabel}
                        />
                      </td>
                    )
                  })}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    )
  }

  // Render Mobile
  const renderMobileDayAnchors = () => (
    <div className="flex gap-2 overflow-x-auto pb-2 px-1 scrollbar-hide">
      {weekdayBackend.map((day, i) => (
        <Badge
          key={day}
          as="button"
          variant={hasToday && i === todayIdx ? "solid" : "outline"}
          tone={hasToday && i === todayIdx ? "primary" : "default"}
          className="chip-day shrink-0 font-semibold transition-all duration-200 hover:scale-105"
          onClick={() =>
            dayCardRefs.current[i]?.scrollIntoView({ behavior: "smooth", block: "start" })
          }
        >
          {weekdayShort[i] ?? getDayLabel(day)}
        </Badge>
      ))}
    </div>
  )

  const renderMobileCards = () => (
    <div className="mt-2 flex w-full flex-col gap-6">
      {renderMobileDayAnchors()}
      {weekdayBackend.map((day, dayIdx) => {
        const label = weekdayLabels[dayIdx] ?? day
        const lessons = filteredSchedule
          .filter((l) => l.weekday === day)
          .sort((a, b) => getTimeStr(a).localeCompare(getTimeStr(b)))
        const isToday = hasToday && dayIdx === todayIdx
        return (
          <DayColumn
            key={day}
            ref={(el: HTMLDivElement | null) => {
              dayCardRefs.current[dayIdx] = el
            }}
            day={day}
            label={label}
            lessons={lessons}
            isToday={isToday}
            isOnline={isOnline}
            hasSchedule={groupSchedule.length > 0}
            userRole={user?.role}
            conflictedIds={conflictedIds}
            onAdd={() => {
              setAddDay(day)
              setAddDialogOpen(true)
            }}
            onLessonOpen={(l) => {
              setDialogLesson(l)
              setOpenDialog(true)
            }}
            onLessonDelete={handleDeleteLesson}
            onRetry={refresh}
            getLessonTypeColor={getLessonTypeColor}
            getLessonTypeLabel={getLessonTypeLabel}
          />
        )
      })}
    </div>
  )

  const inputClass =
    "w-full rounded-xl border border-glass-border bg-surface/40 px-4 py-3 text-[0.98rem] font-medium text-primary-text shadow-sm focus:border-brand focus:outline-none transition-all"

  const activeGroupName = groups.find((g) => g.id === selectedGroup)?.name || ""

  if (isLoading) {
    return (
      <Layout>
        <PageFadeIn>
          <ScheduleSkeleton />
        </PageFadeIn>
      </Layout>
    )
  }

  return (
    <Layout>
      <PageFadeIn>
        <div className="w-full min-h-screen bg-transparent text-primary-text py-8 sm:py-10">
          <div className="mb-6 mt-0 px-2 md:px-4">
            <div
              data-fade
              style={fadeDelayStyle("80ms")}
              className="mb-8 flex flex-wrap items-center gap-4 sm:gap-5"
            >
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-surface/40 border border-glass-border text-brand shadow-glass">
                <CalendarMonthIcon className="h-7 w-7" />
              </div>
              <h1 className="text-[clamp(1.6rem,5vw,2.75rem)] font-bold tracking-tight text-primary-text">
                {user?.role === "student"
                  ? t("schedule:title.student")
                  : t("schedule:title.default")}
              </h1>
              {activeGroupName && (
                <Badge variant="outline" tone="primary" className="translate-y-0.5">
                  {t("schedule:header.groupName", { name: activeGroupName })}
                </Badge>
              )}
            </div>

            <div data-fade style={fadeDelayStyle("140ms")} className="mb-6">
              <WeekSelector currentParity={currentParity} setCurrentParity={setCurrentParity} />
            </div>

            <div
              data-fade
              style={fadeDelayStyle("200ms")}
              className={cn(
                "no-print group relative isolate mb-6 overflow-hidden rounded-3xl border border-glass-border bg-surface/40 p-6 shadow-glass backdrop-blur-md transition-all hover:shadow-xl",
                !isMobile && "max-w-4xl"
              )}
            >
              {currentLesson ? (
                <div className="relative z-1">
                  <div className="mb-4 flex flex-wrap items-center gap-3">
                    <Badge size="sm" tone="primary" className="font-semibold">
                      {t("schedule:chips.current")}
                    </Badge>
                    <h3 className="text-lg font-extrabold">{currentLesson.subject}</h3>
                    {timeLeftText && <Badge size="sm">{timeLeftText}</Badge>}
                  </div>
                  <ProgressBar value={currentProgress} className="mt-5 h-2.5 rounded-full" />
                </div>
              ) : nextLesson ? (
                <div className="relative z-1 flex flex-wrap items-center gap-3">
                  <Badge size="sm" variant="outline" tone="primary" className="font-semibold">
                    {t("schedule:chips.next")}
                  </Badge>
                  <h3 className="text-lg font-extrabold">{nextLesson.subject}</h3>
                  {timeLeftText && <Badge size="sm">{timeLeftText}</Badge>}
                </div>
              ) : (
                <p>{t("schedule:summary.noMoreToday")}</p>
              )}
            </div>

            {(user?.role === "teacher" || user?.role === "admin") && (
              <div data-fade style={fadeDelayStyle("240ms")} className="mb-6 max-w-[380px]">
                <label className="mb-2 block text-sm font-semibold">
                  {t("schedule:form.groupLabel")}
                </label>
                <select
                  value={selectedGroup ?? ""}
                  onChange={(e) => setSelectedGroup(e.target.value || null)}
                  className={inputClass}
                >
                  {groups.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>

          <div data-fade style={fadeDelayStyle("280ms")} className="max-w-[1920px] px-2 md:px-4">
            {isMobile ? renderMobileCards() : renderTable()}
          </div>

          <Dialog
            open={openDialog}
            onClose={() => setOpenDialog(false)}
            maxWidth="sm"
            fullWidth
          >
            <DialogTitle>
              {dialogLesson?.subject || t("schedule:dialog.detailsFallback")}
            </DialogTitle>
            <DialogContent className="space-y-4 pt-2">
              {dialogLesson && (
                <div className="space-y-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold opacity-70 uppercase tracking-wider">
                      {t("schedule:dialog.typeLabel")}:
                    </span>
                    <Badge
                      style={{
                        background: getLessonTypeColor(dialogLesson.lesson_type),
                        color: "#fff",
                      }}
                    >
                      {getLessonTypeLabel(dialogLesson.lesson_type)}
                    </Badge>
                  </div>
                  <div className="space-y-1">
                    <span className="text-sm font-semibold opacity-70 uppercase tracking-wider">
                      {t("schedule:dialog.timeLabel")}:
                    </span>
                    <p className="font-medium">
                      {`${getTimeStr(dialogLesson)}–${getEndTimeStr(dialogLesson)}`}
                    </p>
                  </div>
                  {/* .. more details .. */}
                </div>
              )}
            </DialogContent>
            <DialogActions>
              {(user?.role === "admin" || user?.role === "teacher") && (
                <Button
                  variant="outline"
                  onClick={() => {
                    setEditLesson(dialogLesson)
                    setEditing(true)
                  }}
                >
                  {t("common:buttons.edit")}
                </Button>
              )}
              <Button variant="ghost" onClick={() => setOpenDialog(false)}>
                {t("common:buttons.close")}
              </Button>
            </DialogActions>
          </Dialog>

          <Dialog
            open={editing}
            onClose={() => setEditing(false)}
            maxWidth="sm"
            fullWidth
          >
            <DialogTitle>{t("schedule:dialog.editTitle")}</DialogTitle>
            <DialogContent className="space-y-5 pt-4">
              {editLesson && (
                <div className="space-y-5">
                  <div>
                    <label className="mb-2 block text-sm font-semibold opacity-70">
                      {t("schedule:form.subject")}
                    </label>
                    <input
                      type="text"
                      value={editLesson.subject || ""}
                      onChange={(e) =>
                        setEditLesson((prev) => (prev ? { ...prev, subject: e.target.value } : null))
                      }
                      className={inputClass}
                    />
                  </div>
                  <div>
                    <label className="mb-2 block text-sm font-semibold opacity-70">
                      {t("schedule:form.teacher")}
                    </label>
                    <input
                      type="text"
                      value={editLesson.teacher || ""}
                      onChange={(e) =>
                        setEditLesson((prev) => (prev ? { ...prev, teacher: e.target.value } : null))
                      }
                      className={inputClass}
                    />
                  </div>
                  <div>
                    <label className="mb-2 block text-sm font-semibold opacity-70">
                      {t("schedule:form.room")}
                    </label>
                    <input
                      type="text"
                      value={editLesson.room || ""}
                      onChange={(e) =>
                        setEditLesson((prev) => (prev ? { ...prev, room: e.target.value } : null))
                      }
                      className={inputClass}
                    />
                  </div>
                  <div>
                    <label className="mb-2 block text-sm font-semibold opacity-70">
                      {t("schedule:form.lessonType")}
                    </label>
                    <select
                      value={editLesson.lesson_type || ""}
                      onChange={(e) =>
                        setEditLesson((prev) =>
                          prev ? { ...prev, lesson_type: e.target.value } : null
                        )
                      }
                      className={inputClass}
                    >
                      {editingLessonTypeOptions.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="flex gap-4">
                    <div className="w-1/2">
                      <label className="mb-2 block text-sm font-semibold opacity-70">
                        {t("schedule:form.startTime")}
                      </label>
                      <input
                        type="time"
                        value={getTimeStr(editLesson)}
                        onChange={(e) =>
                          setEditLesson((prev) =>
                            prev
                              ? {
                                  ...prev,
                                  start_time: dayjs().format("YYYY-MM-DDT") + e.target.value + ":00",
                                }
                              : null
                          )
                        }
                        className={inputClass}
                      />
                    </div>
                    <div className="w-1/2">
                      <label className="mb-2 block text-sm font-semibold opacity-70">
                        {t("schedule:form.endTime")}
                      </label>
                      <input
                        type="time"
                        value={getEndTimeStr(editLesson)}
                        onChange={(e) =>
                          setEditLesson((prev) =>
                            prev
                              ? {
                                  ...prev,
                                  end_time: dayjs().format("YYYY-MM-DDT") + e.target.value + ":00",
                                }
                              : null
                          )
                        }
                        className={inputClass}
                      />
                    </div>
                  </div>
                  <div>
                    <label className="mb-2 block text-sm font-semibold opacity-70">
                      {t("schedule:form.week")}
                    </label>
                    <select
                      value={editLesson.parity}
                      onChange={(e) =>
                        setEditLesson((prev) =>
                          prev ? { ...prev, parity: e.target.value as LessonParity } : null
                        )
                      }
                      className={inputClass}
                    >
                      <option value="both">{t("schedule:week.both")}</option>
                      <option value="odd">{t("schedule:week.odd")}</option>
                      <option value="even">{t("schedule:week.even")}</option>
                    </select>
                  </div>
                </div>
              )}
            </DialogContent>
            <DialogActions>
              <Button variant="ghost" onClick={() => setEditing(false)}>
                {t("common:buttons.cancel")}
              </Button>
              <Button
                variant="solid"
                onClick={async () => {
                  if (!editLesson) return
                  const optimisticId = editLesson.id
                  const backup = groupSchedule.map((l) => ({ ...l }))
                  const backendLessonType = toBackendLessonType(editLesson.lesson_type)
                  const updatedLesson = { ...editLesson, lesson_type: backendLessonType }
                  applyScheduleUpdate((prev) =>
                    prev.map((l) => (l.id === optimisticId ? updatedLesson : l))
                  )
                  try {
                    await api.patch(`/schedule/${optimisticId}`, {
                      ...editLesson,
                      lesson_type: backendLessonType,
                    })
                    setSnack(t("schedule:snackbar.updated"))
                    setEditing(false)
                    setOpenDialog(false)
                    refresh()
                  } catch {
                    setSnack(t("schedule:snackbar.updateError"))
                    applyScheduleUpdate(() => backup)
                  }
                }}
              >
                {t("common:buttons.save")}
              </Button>
            </DialogActions>
          </Dialog>

          <Dialog
            open={addDialogOpen}
            onClose={() => setAddDialogOpen(false)}
            maxWidth="sm"
            fullWidth
          >
            <DialogTitle>{t("schedule:dialog.addTitle")}</DialogTitle>
            <DialogContent className="space-y-5 pt-4">
              <div className="space-y-5">
                <div>
                  <label className="mb-2 block text-sm font-semibold opacity-70">
                    {t("schedule:form.subject")}
                  </label>
                  <input
                    value={addFields.subject}
                    onChange={(e) => setAddFields({ ...addFields, subject: e.target.value })}
                    className={inputClass}
                  />
                </div>
                <div>
                  <label className="mb-2 block text-sm font-semibold opacity-70">
                    {t("schedule:form.teacher")}
                  </label>
                  <input
                    value={addFields.teacher}
                    onChange={(e) => setAddFields({ ...addFields, teacher: e.target.value })}
                    className={inputClass}
                  />
                </div>
                <div>
                  <label className="mb-2 block text-sm font-semibold opacity-70">
                    {t("schedule:form.room")}
                  </label>
                  <input
                    value={addFields.room}
                    onChange={(e) => setAddFields({ ...addFields, room: e.target.value })}
                    className={inputClass}
                  />
                </div>
                <div>
                  <label className="mb-2 block text-sm font-semibold opacity-70">
                    {t("schedule:form.lessonType")}
                  </label>
                  <select
                    value={addFields.lessonType}
                    onChange={(e) => setAddFields({ ...addFields, lessonType: e.target.value })}
                    className={inputClass}
                  >
                    {lessonTypeOptions.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex gap-4">
                  <div className="w-1/2">
                    <label className="mb-2 block text-sm font-semibold opacity-70">
                      {t("schedule:form.startTime")}
                    </label>
                    <input
                      type="time"
                      value={addFields.startTime}
                      onChange={(e) => setAddFields({ ...addFields, startTime: e.target.value })}
                      className={inputClass}
                    />
                  </div>
                  <div className="w-1/2">
                    <label className="mb-2 block text-sm font-semibold opacity-70">
                      {t("schedule:form.endTime")}
                    </label>
                    <input
                      type="time"
                      value={addFields.endTime}
                      onChange={(e) => setAddFields({ ...addFields, endTime: e.target.value })}
                      className={inputClass}
                    />
                  </div>
                </div>
                <div>
                  <label className="mb-2 block text-sm font-semibold opacity-70">
                    {t("schedule:form.week")}
                  </label>
                  <select
                    value={addFields.parity}
                    onChange={(e) =>
                      setAddFields({ ...addFields, parity: e.target.value as LessonParity })
                    }
                    className={inputClass}
                  >
                    <option value="both">{t("schedule:week.both")}</option>
                    <option value="odd">{t("schedule:week.odd")}</option>
                    <option value="even">{t("schedule:week.even")}</option>
                  </select>
                </div>
              </div>
            </DialogContent>
            <DialogActions>
              <Button variant="ghost" onClick={() => setAddDialogOpen(false)}>
                {t("common:buttons.cancel")}
              </Button>
              <Button variant="solid" onClick={handleAddLesson}>
                {t("schedule:buttons.add")}
              </Button>
            </DialogActions>
          </Dialog>

          <Snackbar open={!!snack} onClose={() => setSnack("")}>
            <Alert onClose={() => setSnack("")} severity="info">
              {snack}
            </Alert>
          </Snackbar>
        </div>
      </PageFadeIn>
    </Layout>
  )

  async function handleAddLesson() {
    const { subject, teacher, room, lessonType, startTime, endTime, parity } = addFields
    if (!subject || !teacher || !room || !addDay || !startTime || !endTime || !selectedGroup) {
      setSnack(t("schedule:snackbar.fillAllFields"))
      return
    }
    const backendLessonType = toBackendLessonType(lessonType)
    const optimistic: Lesson = {
      id: `temp-${Date.now()}`,
      group_id: selectedGroup,
      subject,
      teacher,
      room,
      lesson_type: backendLessonType,
      weekday: addDay,
      start_time: dayjs().format("YYYY-MM-DDT") + startTime + ":00",
      end_time: dayjs().format("YYYY-MM-DDT") + endTime + ":00",
      parity,
    }
    applyScheduleUpdate((prev) => [...prev, optimistic])
    try {
      await api.post("/schedule", {
        group_id: selectedGroup,
        subject,
        teacher,
        room,
        lesson_type: backendLessonType,
        weekday: addDay,
        start_time: optimistic.start_time,
        end_time: optimistic.end_time,
        parity,
      })
      setSnack(t("schedule:snackbar.added"))
      setAddDialogOpen(false)
      refresh()
    } catch {
      setSnack(t("schedule:snackbar.addError"))
      applyScheduleUpdate((prev) => prev.filter((l) => l.id !== optimistic.id))
    }
  }

  async function handleDeleteLesson(id: string) {
    const backup = groupSchedule.map((l) => ({ ...l }))
    applyScheduleUpdate((prev) => prev.filter((l) => l.id !== id))
    try {
      await api.delete(`/schedule/${id}`)
      refresh()
      setSnack(t("schedule:snackbar.deleted"))
    } catch {
      setSnack(t("schedule:snackbar.deleteError"))
      applyScheduleUpdate(() => backup)
    }
  }
}
