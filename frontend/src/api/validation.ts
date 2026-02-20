import { safeParse, type GenericSchema, type BaseIssue, flatten, type InferOutput } from "valibot"

export class ApiResponseValidationError extends Error {
  public readonly issues: BaseIssue<unknown>[]
  override readonly name = "ApiResponseValidationError"

  constructor(
    issues: BaseIssue<unknown>[],
    context?: string
  ) {
    // Generate a readable error message from issues
    // flatten expects a non-empty array tuple, which we can assert here
    // because Validation Error is only thrown when there ARE issues.
    const flat = flatten(issues as [BaseIssue<unknown>, ...BaseIssue<unknown>[]])
    const summary = Object.values(flat.nested || {}).flat().join(", ") || flat.root?.join(", ") || "Validation failed"
    super(context ? `Invalid API response for ${context}: ${summary}` : `Invalid API response: ${summary}`)
    this.issues = issues
  }
}

export const ensureValidResponse = <T extends GenericSchema<unknown, unknown>>(
  schema: T,
  data: unknown,
  context?: string
): InferOutput<T> => {
  const result = safeParse(schema, data)
  if (!result.success) {
    throw new ApiResponseValidationError(result.issues, context)
  }
  return result.output as InferOutput<T>
}
