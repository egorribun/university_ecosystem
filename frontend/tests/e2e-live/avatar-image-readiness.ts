export type ExistingImageDecodeOutcome = "resolved" | "rejected" | "timeout" | "unavailable"

export type ExistingImageDecodeResult =
  | {
      outcome: "resolved"
      naturalWidth: number | null
      naturalHeight: number | null
    }
  | {
      outcome: "rejected" | "timeout" | "unavailable"
      naturalWidth: null
      naturalHeight: null
    }

type ExistingImageTarget =
  HTMLElement | SVGElement | Pick<HTMLImageElement, "decode" | "naturalWidth" | "naturalHeight">

/**
 * This callback is passed directly to Playwright Locator.evaluate, so it must
 * remain self-contained and may only inspect the existing image element.
 */
export async function decodeExistingImage(
  element: ExistingImageTarget,
  requestedTimeoutMs: number
): Promise<ExistingImageDecodeResult> {
  const image = element as Partial<
    Pick<HTMLImageElement, "decode" | "naturalWidth" | "naturalHeight">
  >
  const unavailable = {
    outcome: "unavailable" as const,
    naturalWidth: null,
    naturalHeight: null,
  }
  if (!image || typeof image.decode !== "function") return unavailable

  const timeoutMs = Number.isFinite(requestedTimeoutMs)
    ? Math.min(2000, Math.max(1, Math.floor(requestedTimeoutMs)))
    : 2000
  const boundedDimension = (value: number | undefined): number | null =>
    typeof value === "number" && Number.isFinite(value) && value >= 0
      ? Math.min(32768, Math.floor(value))
      : null

  let decodeResult: Promise<ExistingImageDecodeResult>
  try {
    decodeResult = image.decode().then(
      () => ({
        outcome: "resolved" as const,
        naturalWidth: boundedDimension(image.naturalWidth),
        naturalHeight: boundedDimension(image.naturalHeight),
      }),
      () => ({
        outcome: "rejected" as const,
        naturalWidth: null,
        naturalHeight: null,
      })
    )
  } catch {
    return {
      outcome: "rejected",
      naturalWidth: null,
      naturalHeight: null,
    }
  }

  let timer: ReturnType<typeof globalThis.setTimeout> | undefined
  const timeoutResult = new Promise<ExistingImageDecodeResult>((resolve) => {
    timer = globalThis.setTimeout(
      () =>
        resolve({
          outcome: "timeout",
          naturalWidth: null,
          naturalHeight: null,
        }),
      timeoutMs
    )
  })

  try {
    return await Promise.race([decodeResult, timeoutResult])
  } finally {
    if (timer !== undefined) globalThis.clearTimeout(timer)
  }
}
