import { useState, useEffect, useRef, useDeferredValue, startTransition } from "react"
import { PageLayout } from "@/components/PageLayout"
import dayjs from "dayjs"
import isoWeek from "dayjs/plugin/isoWeek"
import "dayjs/locale/ru"
import "dayjs/locale/en"
import { useTranslation } from "react-i18next"
import { Button, Badge, ProgressBar, Input, Select } from "@/components/ui"
import {
  Alert,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Snackbar,
} from "@/components/settings"
import { Calendar as CalendarMonthIcon, Plus as AddIcon } from "lucide-react"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"
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
} from "@/components/schedule/scheduleUtils"
import { useScheduleData } from "@/hooks/useScheduleData"
import { LessonCard } from "@/components/schedule/LessonCard"
import { WeekSelector } from "@/components/schedule/WeekSelector"
import { DayColumn } from "@/components/schedule/DayColumn"
import { ScheduleSkeleton } from "@/components/schedule/ScheduleSkeleton"
import FadeSection from "@/components/FadeSection"

dayjs.extend(isoWeek)

export default function Schedule() {
  const { t } = useTranslation(["schedule", "common"])
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
    currentLesson,
    nextLesson,
    conflictedIds,
    timeLeftText,
    currentProgress,
  } = useScheduleData()

  const [snackbar, setSnackbar] = useState("")
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

  const isMobile = useMediaQuery(`(max-width: ${breakpoints.ultrawide})`)
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
    setRowLimit(() => {
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
      <div className="absolute left-1/2 top-[-14px] z-(--z-deep) -translate-x-1/2 pointer-events-none">
        <Badge
          size="xs"
          className="chip-break font-medium bg-(--bg-surface)/(--opacity-hover) border-glass-border shadow-glass text-(--text-secondary)"
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
        className="mx-auto w-full max-w-[min(98vw,1920px)] overflow-x-auto rounded-lg border border-glass-border bg-(--bg-surface)/(--opacity-medium) text-(--text-primary) shadow-glass backdrop-blur-md scroll-smooth min-h-[360px]"
      >
        <table className="w-full border-collapse">
          <thead className="sticky top-0 z-(--z-content)">
            <tr>
              <th className="sticky left-0 z-(--z-navbar) w-[50px] bg-(--bg-surface)/(--opacity-strong) px-4 py-4 text-center font-extrabold text-(--text-primary) border-r border-glass-border shadow-md backdrop-blur-md">
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
                      isTodayCol
                        ? "bg-brand/(--opacity-subtle) shadow-focus"
                        : "bg-(--bg-surface)/(--opacity-medium)",
                      "z-(--z-navbar) backdrop-blur-md"
                    )}
                  >
                    <div className="flex items-center justify-center gap-2">
                      <span className={cn("tracking-tight", isTodayCol && "text-brand")}>
                        {label}
                      </span>
                      {(user?.role === "admin" || user?.role === "teacher") && (
                        <button
                          className="ml-1 flex h-7 w-7 items-center justify-center rounded-xs border border-glass-border bg-(--bg-surface)/(--opacity-strong) text-brand hover:bg-brand hover:text-white transition-colors"
                          onClick={(event) => {
                            event.stopPropagation()
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
                  <td className="sticky left-0 z-(--z-navbar) bg-(--bg-surface)/(--opacity-strong) px-4 py-3 text-center font-bold border-r border-glass-border shadow-md backdrop-blur-md">
                    {rowIdx + 1}
                  </td>
                  {row.map((lesson, colIdx) => {
                    const colIsToday = hasToday && colIdx === todayIdx
                    if (!lesson) {
                      return (
                        <td
                          key={`empty-${rowIdx}-${colIdx}`}
                          className={cn("p-3", colIsToday ? "bg-card-hover" : "")}
                        >
                          <div className="min-h-[148px] rounded-sm border border-dashed border-card-border" />
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
                          colIsToday ? "bg-brand/(--opacity-faint)" : ""
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

  const activeGroupName = groups.find((g) => g.id === selectedGroup)?.name || ""

  if (isLoading) {
    return (
      <PageLayout variant="wide">
        <ScheduleSkeleton />
      </PageLayout>
    )
  }

  return (
    <PageLayout variant="wide">
      <div className="w-full text-(--text-primary)">
        <div className="mb-6 mt-0">
          <header>
            <FadeSection delay="80ms" className="mb-8 flex flex-wrap items-center gap-4 sm:gap-5">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-(--bg-surface)/(--opacity-medium) border border-glass-border text-brand shadow-glass">
                <CalendarMonthIcon className="h-7 w-7" />
              </div>
              <h1 className="text-(length:--fs-page-title) font-bold tracking-tight text-(--text-primary)">
                {user?.role === "student"
                  ? t("schedule:title.student")
                  : t("schedule:title.default")}
              </h1>
              {activeGroupName && (
                <Badge variant="outline" tone="primary" className="translate-y-0.5">
                  {t("schedule:header.groupName", { name: activeGroupName })}
                </Badge>
              )}
            </FadeSection>

            <FadeSection delay="140ms" className="mb-6">
              <WeekSelector currentParity={currentParity} setCurrentParity={setCurrentParity} />
            </FadeSection>

            <FadeSection
              delay="200ms"
              className={cn(
                "no-print group relative isolate mb-6 overflow-hidden rounded-lg border border-glass-border bg-(--bg-surface)/(--opacity-medium) p-6 shadow-glass backdrop-blur-md transition-all hover:shadow-xl",
                !isMobile && "max-w-4xl"
              )}
            >
              {currentLesson ? (
                <div className="relative z-(--z-base)">
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
                <div className="relative z-(--z-base) flex flex-wrap items-center gap-3">
                  <Badge size="sm" variant="outline" tone="primary" className="font-semibold">
                    {t("schedule:chips.next")}
                  </Badge>
                  <h3 className="text-lg font-extrabold">{nextLesson.subject}</h3>
                  {timeLeftText && <Badge size="sm">{timeLeftText}</Badge>}
                </div>
              ) : (
                <p>{t("schedule:summary.noMoreToday")}</p>
              )}
            </FadeSection>

            {(user?.role === "teacher" || user?.role === "admin") && (
              <FadeSection delay="240ms" className="mb-6 max-w-[380px]">
                <label className="mb-2 block text-sm font-semibold">
                  {t("schedule:form.groupLabel")}
                </label>
                <Select
                  value={selectedGroup ?? ""}
                  onValueChange={(val) => setSelectedGroup(val || null)}
                  options={groups.map((g) => ({ value: g.id, label: g.name }))}
                  placeholder={t("schedule:form.groupLabel")}
                />
              </FadeSection>
            )}
          </header>
        </div>

        <section aria-label={t("schedule:title.default")}>
          <FadeSection delay="280ms" className="max-w-[1920px]">
            {isMobile ? renderMobileCards() : renderTable()}
          </FadeSection>
        </section>

        <Dialog open={openDialog} onClose={() => setOpenDialog(false)} maxWidth="sm" fullWidth>
          <DialogTitle>{dialogLesson?.subject || t("schedule:dialog.detailsFallback")}</DialogTitle>
          <DialogContent className="space-y-4 pt-2">
            {dialogLesson && (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold opacity-(--opacity-strong) uppercase tracking-wider">
                    {t("schedule:dialog.typeLabel")}:
                  </span>
                  <Badge
                    style={{
                      background: getLessonTypeColor(dialogLesson.lesson_type),
                      color: "white",
                    }}
                  >
                    {getLessonTypeLabel(dialogLesson.lesson_type)}
                  </Badge>
                </div>
                <div className="space-y-1">
                  <span className="text-sm font-semibold opacity-(--opacity-strong) uppercase tracking-wider">
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

        <Dialog open={editing} onClose={() => setEditing(false)} maxWidth="sm" fullWidth>
          <DialogTitle>{t("schedule:dialog.editTitle")}</DialogTitle>
          <DialogContent className="space-y-5 pt-4">
            {editLesson && (
              <div className="space-y-5">
                <div>
                  <label className="mb-2 block text-sm font-semibold opacity-(--opacity-strong)">
                    {t("schedule:form.subject")}
                  </label>
                  <Input
                    type="text"
                    value={editLesson.subject || ""}
                    onChange={(event) =>
                      setEditLesson((prev) =>
                        prev ? { ...prev, subject: event.target.value } : null
                      )
                    }
                    fullWidth
                  />
                </div>
                <div>
                  <label className="mb-2 block text-sm font-semibold opacity-(--opacity-strong)">
                    {t("schedule:form.teacher")}
                  </label>
                  <Input
                    type="text"
                    value={editLesson.teacher || ""}
                    onChange={(event) =>
                      setEditLesson((prev) =>
                        prev ? { ...prev, teacher: event.target.value } : null
                      )
                    }
                    fullWidth
                  />
                </div>
                <div>
                  <label className="mb-2 block text-sm font-semibold opacity-(--opacity-strong)">
                    {t("schedule:form.room")}
                  </label>
                  <Input
                    type="text"
                    value={editLesson.room || ""}
                    onChange={(event) =>
                      setEditLesson((prev) => (prev ? { ...prev, room: event.target.value } : null))
                    }
                    fullWidth
                  />
                </div>
                <div>
                  <label className="mb-2 block text-sm font-semibold opacity-(--opacity-strong)">
                    {t("schedule:form.lessonType")}
                  </label>
                  <Select
                    value={editLesson.lesson_type || ""}
                    onValueChange={(val) =>
                      setEditLesson((prev) => (prev ? { ...prev, lesson_type: val } : null))
                    }
                    options={editingLessonTypeOptions.map((o) => ({
                      value: o.value,
                      label: o.label,
                    }))}
                    placeholder={t("schedule:form.lessonType")}
                  />
                </div>
                <div className="flex gap-4">
                  <div className="w-1/2">
                    <label className="mb-2 block text-sm font-semibold opacity-(--opacity-strong)">
                      {t("schedule:form.startTime")}
                    </label>
                    <Input
                      type="time"
                      value={getTimeStr(editLesson)}
                      onChange={(event) =>
                        setEditLesson((prev) =>
                          prev
                            ? {
                                ...prev,
                                start_time:
                                  dayjs().format("YYYY-MM-DDT") + event.target.value + ":00",
                              }
                            : null
                        )
                      }
                      fullWidth
                    />
                  </div>
                  <div className="w-1/2">
                    <label className="mb-2 block text-sm font-semibold opacity-(--opacity-strong)">
                      {t("schedule:form.endTime")}
                    </label>
                    <Input
                      type="time"
                      value={getEndTimeStr(editLesson)}
                      onChange={(event) =>
                        setEditLesson((prev) =>
                          prev
                            ? {
                                ...prev,
                                end_time:
                                  dayjs().format("YYYY-MM-DDT") + event.target.value + ":00",
                              }
                            : null
                        )
                      }
                      fullWidth
                    />
                  </div>
                </div>
                <div>
                  <label className="mb-2 block text-sm font-semibold opacity-(--opacity-strong)">
                    {t("schedule:form.week")}
                  </label>
                  <Select
                    value={editLesson.parity}
                    onValueChange={(val) =>
                      setEditLesson((prev) =>
                        prev ? { ...prev, parity: val as LessonParity } : null
                      )
                    }
                    options={[
                      { value: "both", label: t("schedule:week.both") },
                      { value: "odd", label: t("schedule:week.odd") },
                      { value: "even", label: t("schedule:week.even") },
                    ]}
                    placeholder={t("schedule:form.week")}
                  />
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
                const backup = groupSchedule.map((lesson) => ({ ...lesson }))
                const backendLessonType = toBackendLessonType(editLesson.lesson_type)
                const updatedLesson = { ...editLesson, lesson_type: backendLessonType }
                applyScheduleUpdate((prev) =>
                  prev.map((lesson) => (lesson.id === optimisticId ? updatedLesson : lesson))
                )
                try {
                  await api.patch(`/schedule/${optimisticId}`, {
                    ...editLesson,
                    lesson_type: backendLessonType,
                  })
                  setSnackbar(t("schedule:snackbar.updated"))
                  setEditing(false)
                  setOpenDialog(false)
                  refresh()
                } catch {
                  setSnackbar(t("schedule:snackbar.updateError"))
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
                <label className="mb-2 block text-sm font-semibold opacity-(--opacity-strong)">
                  {t("schedule:form.subject")}
                </label>
                <Input
                  value={addFields.subject}
                  onChange={(event) => setAddFields({ ...addFields, subject: event.target.value })}
                  fullWidth
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-semibold opacity-(--opacity-strong)">
                  {t("schedule:form.teacher")}
                </label>
                <Input
                  value={addFields.teacher}
                  onChange={(event) => setAddFields({ ...addFields, teacher: event.target.value })}
                  fullWidth
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-semibold opacity-(--opacity-strong)">
                  {t("schedule:form.room")}
                </label>
                <Input
                  value={addFields.room}
                  onChange={(event) => setAddFields({ ...addFields, room: event.target.value })}
                  fullWidth
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-semibold opacity-(--opacity-strong)">
                  {t("schedule:form.lessonType")}
                </label>
                <Select
                  value={addFields.lessonType}
                  onValueChange={(val) => setAddFields({ ...addFields, lessonType: val })}
                  options={lessonTypeOptions.map((o) => ({ value: o.value, label: o.label }))}
                  placeholder={t("schedule:form.lessonType")}
                />
              </div>
              <div className="flex gap-4">
                <div className="w-1/2">
                  <label className="mb-2 block text-sm font-semibold opacity-(--opacity-strong)">
                    {t("schedule:form.startTime")}
                  </label>
                  <Input
                    type="time"
                    value={addFields.startTime}
                    onChange={(event) =>
                      setAddFields({ ...addFields, startTime: event.target.value })
                    }
                    fullWidth
                  />
                </div>
                <div className="w-1/2">
                  <label className="mb-2 block text-sm font-semibold opacity-(--opacity-strong)">
                    {t("schedule:form.endTime")}
                  </label>
                  <Input
                    type="time"
                    value={addFields.endTime}
                    onChange={(event) =>
                      setAddFields({ ...addFields, endTime: event.target.value })
                    }
                    fullWidth
                  />
                </div>
              </div>
              <div>
                <label className="mb-2 block text-sm font-semibold opacity-(--opacity-strong)">
                  {t("schedule:form.week")}
                </label>
                <Select
                  value={addFields.parity}
                  onValueChange={(val) =>
                    setAddFields({ ...addFields, parity: val as LessonParity })
                  }
                  options={[
                    { value: "both", label: t("schedule:week.both") },
                    { value: "odd", label: t("schedule:week.odd") },
                    { value: "even", label: t("schedule:week.even") },
                  ]}
                  placeholder={t("schedule:form.week")}
                />
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

        <Snackbar
          open={!!snackbar}
          autoHideDuration={4000}
          onClose={() => setSnackbar("")}
          anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
        >
          <Alert severity="success" onClose={() => setSnackbar("")}>
            {snackbar}
          </Alert>
        </Snackbar>
      </div>
    </PageLayout>
  )

  async function handleAddLesson() {
    const { subject, teacher, room, lessonType, startTime, endTime, parity } = addFields
    if (!subject || !teacher || !room || !addDay || !startTime || !endTime || !selectedGroup) {
      setSnackbar(t("schedule:snackbar.fillAllFields"))
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
      setSnackbar(t("schedule:snackbar.added"))
      setAddDialogOpen(false)
      refresh()
    } catch {
      setSnackbar(t("schedule:snackbar.addError"))
      applyScheduleUpdate((prev) => prev.filter((l) => l.id !== optimistic.id))
    }
  }

  async function handleDeleteLesson(id: string) {
    const backup = groupSchedule.map((l) => ({ ...l }))
    applyScheduleUpdate((prev) => prev.filter((l) => l.id !== id))
    try {
      await api.delete(`/schedule/${id}`)
      refresh()
      setSnackbar(t("schedule:snackbar.deleted"))
    } catch {
      setSnackbar(t("schedule:snackbar.deleteError"))
      applyScheduleUpdate(() => backup)
    }
  }
}
