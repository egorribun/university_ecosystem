import { AxiosHeaders } from "axios"
import type { AxiosResponse } from "axios"
import { setTraceContext } from "@/app/logger"

const TRACE_HEADER = (import.meta.env.VITE_TRACE_HEADER || "x-trace-id") as string

export const updateTraceContext = (headers: AxiosResponse["headers"] | undefined) => {
  // AxiosHeaders#get already performs case-insensitive lookup. Passing an
  // empty object for an absent response keeps the interceptor total during
  // error/SSR paths without a second, redundant fallback lookup.
  const normalized = AxiosHeaders.from(Object.assign({}, headers) as AxiosHeaders)
  const rawTraceId = normalized.get(TRACE_HEADER)
  const traceId = typeof rawTraceId === "string" ? rawTraceId.trim() : ""
  setTraceContext(traceId || null)
}
