import * as v from "valibot"
import { resolveSsrBackendOrigin } from "@/api/backendOrigin"

/** Match the API client's deadline so a stalled config service cannot hold SSR. */
const CAMPUS_CONFIG_REQUEST_TIMEOUT_MS = 8_000

const CampusConfigSchema = v.pipe(
  v.strictObject({ campus_timezone: v.pipe(v.string(), v.minLength(1)) }),
  v.check(({ campus_timezone }) => {
    try {
      new Intl.DateTimeFormat("en", { timeZone: campus_timezone })
      return true
    } catch {
      return false
    }
  }, "campus_timezone must be a supported IANA timezone")
)

/** Read only the public campus setting; never infer it from the browser or a frontend env. */
export async function fetchCampusTimezone(): Promise<string | null> {
  try {
    const url =
      typeof window === "undefined"
        ? `${resolveSsrBackendOrigin()}/api/v1/campus/config`
        : "/api/v1/campus/config"
    const response = await fetch(url, {
      headers: { Accept: "application/json" },
      cache: "no-store",
      signal: AbortSignal.timeout(CAMPUS_CONFIG_REQUEST_TIMEOUT_MS),
    })
    if (!response.ok) return null
    const parsed = v.safeParse(CampusConfigSchema, await response.json())
    return parsed.success ? parsed.output.campus_timezone : null
  } catch {
    return null
  }
}
