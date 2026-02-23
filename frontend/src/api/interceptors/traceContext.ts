import { AxiosHeaders } from "axios"
import type { AxiosResponse } from "axios"
import { setTraceContext } from "@/app/logger"

const TRACE_HEADER = (import.meta.env.VITE_TRACE_HEADER || "x-trace-id") as string

export const updateTraceContext = (headers: AxiosResponse["headers"] | undefined) => {
  if (!headers) {
    setTraceContext(null)
    return
  }
  const normalized = AxiosHeaders.from(headers as AxiosHeaders)
  const traceId = normalized.get(TRACE_HEADER) ?? normalized.get(TRACE_HEADER.toLowerCase())
  if (typeof traceId === "string" && traceId.trim()) {
    setTraceContext(traceId)
  } else {
    setTraceContext(null)
  }
}
