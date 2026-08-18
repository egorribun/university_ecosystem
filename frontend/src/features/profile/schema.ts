import * as v from "valibot"

const editField = v.fallback(
  v.optional(
    v.pipe(
      v.union([v.literal("1"), v.literal(1)]),
      v.transform(() => "1" as const)
    )
  ),
  undefined
)

export const profileSearchSchema = v.object({
  edit: editField,
})

export type ProfileSearch = v.InferOutput<typeof profileSearchSchema>
