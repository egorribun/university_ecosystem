import { isAxiosError } from "axios"
import { ApiResponseValidationError } from "@/api/validation"

export interface ApiErrorDetail {
  code: string
  message: string
  field?: string
}

export interface ApiErrorResponse {
  status: number
  message: string
  details?: ApiErrorDetail[]
  traceId?: string
}

/**
 * Extracts a normalized error response from any caught exception.
 */
export const extractApiError = (
  error: unknown,
  fallbackMessage = "An unexpected error occurred"
): ApiErrorResponse => {
  if (isAxiosError(error)) {
    const data = error.response?.data as Record<string, unknown> | undefined
    const status = error.response?.status || 0

    // Extract standard FastAPI / internal error formats
    const message =
      typeof data?.detail === "string"
        ? data.detail
        : typeof data?.message === "string"
          ? data.message
          : error.message || fallbackMessage

    const details: ApiErrorDetail[] = []

    if (Array.isArray(data?.detail)) {
      // Handle FastAPI Pydantic validation errors
      for (const err of data.detail) {
        if (err.msg && err.loc) {
          details.push({
            code: err.type || "validation_error",
            message: err.msg,
            field: Array.isArray(err.loc) ? err.loc[err.loc.length - 1]?.toString() : undefined,
          })
        }
      }
    }

    return {
      status,
      message,
      details: details.length > 0 ? details : undefined,
      traceId: typeof data?.trace_id === "string" ? data.trace_id : undefined,
    }
  }

  if (error instanceof ApiResponseValidationError) {
    return {
      status: 422, // Unprocessable Entity
      message: error.message,
      details: error.issues.map((issue) => ({
        code: issue.type,
        message: issue.message,
        field: issue.path?.map((p) => p.key).join(".") || undefined,
      })),
    }
  }

  if (error instanceof Error) {
    return {
      status: 0,
      message: error.message || fallbackMessage,
    }
  }

  return {
    status: 0,
    message: typeof error === "string" ? error : fallbackMessage,
  }
}

/**
 * Creates a generic fallback function for queries/mutations.
 */
export const createFallback = <T>(fallbackValue: T) => {
  return (_error: unknown): T => {
    return fallbackValue
  }
}
