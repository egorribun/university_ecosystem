/** A closed, non-identifying summary of one blocking task's measurement phase. */
export interface MapZoomDiagnosticSample {
  step: number
  phase: number
  duration: number
}

const MAX_SAMPLES = 8
const MAX_TOTAL = 999
const MAX_DURATION_MS = 60_000

export function reportMapZoomLongTasks(
  project: unknown,
  attempt: unknown,
  samples: readonly MapZoomDiagnosticSample[]
): void {
  if (
    (project !== "desktop" && project !== "mobile") ||
    (attempt !== 0 && attempt !== 1) ||
    !Array.isArray(samples) ||
    samples.length === 0
  ) {
    return
  }

  const total = Math.min(samples.length, MAX_TOTAL)
  for (let index = 0; index < Math.min(samples.length, MAX_SAMPLES); index += 1) {
    const sample: unknown = samples[index]
    if (!sample || typeof sample !== "object") continue
    const { step, phase, duration } = sample as Record<string, unknown>
    if (
      typeof step !== "number" ||
      !Number.isInteger(step) ||
      typeof phase !== "number" ||
      !Number.isInteger(phase) ||
      typeof duration !== "number" ||
      !Number.isFinite(duration) ||
      duration < 50
    ) {
      continue
    }
    const validPhase =
      (step === 0 && phase === 0) ||
      (step >= 1 && step <= 3 && phase >= 1 && phase <= 3) ||
      (step === 3 && phase === 4)
    if (!validPhase) continue

    const durationMs = Math.min(MAX_DURATION_MS, Math.ceil(duration))
    const record =
      `UE_LIVE_MAP_ZOOM_V1 project=${project} attempt=${attempt} sample=${index + 1} ` +
      `total=${total} step=${step} phase=${phase} duration_ms=${durationMs}\n`
    try {
      process.stdout.write(record)
    } catch {
      // A closed diagnostic stream must not replace the original assertion.
    }
  }
}
