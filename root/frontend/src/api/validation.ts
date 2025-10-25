import { ZodError, type ZodType } from "zod"

export class ApiResponseValidationError extends Error {
  override readonly name = "ApiResponseValidationError"

  constructor(public readonly details: ZodError, context?: string) {
    super(context ? `Invalid API response for ${context}` : "Invalid API response")
  }
}

export const ensureValidResponse = <T>(schema: ZodType<T>, data: unknown, context?: string): T => {
  const result = schema.safeParse(data)
  if (!result.success) {
    throw new ApiResponseValidationError(result.error, context)
  }
  return result.data
}
