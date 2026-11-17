import type { Page } from "@playwright/test"

export interface LongTaskSample {
  startTime: number
  duration: number
}

export interface ZoomPhaseMark {
  step: number
  phase: number
  at: number
}

export interface MeasuredLongTaskSample {
  duration: number
  step: number
  phase: number
}

export interface WindowWithMapZoomObserver extends Window {
  __mapZoomLongTaskObserver?: PerformanceObserver
  __mapZoomLongTaskSamples?: LongTaskSample[]
  __mapZoomMeasurementStartedAt?: number
  __mapZoomPhaseMarks?: ZoomPhaseMark[]
}

/** Classify by task start, retaining timing origins only inside the page. */
export async function stopLongTaskMeasurement(page: Page): Promise<MeasuredLongTaskSample[]> {
  return page.evaluate(async () => {
    const measurementWindow = window as WindowWithMapZoomObserver
    const marks = measurementWindow.__mapZoomPhaseMarks ?? []
    marks.push({ step: 3, phase: 4, at: performance.now() })
    await new Promise<void>((resolve) => {
      requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
    })

    const observer = measurementWindow.__mapZoomLongTaskObserver
    const samples = measurementWindow.__mapZoomLongTaskSamples ?? []
    const startedAt = measurementWindow.__mapZoomMeasurementStartedAt ?? Number.POSITIVE_INFINITY

    for (const entry of observer?.takeRecords() ?? []) {
      if (entry.entryType === "longtask") {
        samples.push({ startTime: entry.startTime, duration: entry.duration })
      }
    }
    observer?.disconnect()

    const ordered =
      marks.length === 10 &&
      marks.every((mark, index) => {
        const expectedStep = index === 9 ? 3 : Math.floor(index / 3) + 1
        const expectedPhase = index === 9 ? 4 : (index % 3) + 1
        return (
          mark.step === expectedStep &&
          mark.phase === expectedPhase &&
          Number.isFinite(mark.at) &&
          (index === 0 || mark.at >= marks[index - 1]!.at)
        )
      })
    const zoomSamples = samples.filter((sample) => sample.startTime >= startedAt)
    delete measurementWindow.__mapZoomLongTaskObserver
    delete measurementWindow.__mapZoomLongTaskSamples
    delete measurementWindow.__mapZoomMeasurementStartedAt
    delete measurementWindow.__mapZoomPhaseMarks
    return zoomSamples.map((sample) => {
      let phase: ZoomPhaseMark | undefined
      if (ordered) {
        for (const mark of marks) {
          if (mark.at > sample.startTime) break
          phase = mark
        }
      }
      return { duration: sample.duration, step: phase?.step ?? 0, phase: phase?.phase ?? 0 }
    })
  })
}
