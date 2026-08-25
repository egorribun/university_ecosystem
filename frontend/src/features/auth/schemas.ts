import * as v from "valibot"

export const loginSchema = v.object({
  email: v.pipe(
    v.string(),
    v.minLength(1, "auth:messages.emailRequired"),
    v.email("auth:messages.invalidEmail")
  ),
  password: v.pipe(v.string(), v.minLength(1, "Password is required")),
  rememberEmail: v.optional(v.boolean()),
  trustDevice: v.optional(v.boolean()),
})

export type LoginValues = v.InferInput<typeof loginSchema>

export const registerSchema = v.pipe(
  v.object({
    full_name: v.pipe(v.string(), v.minLength(2, "Name must be at least 2 characters")),
    email: v.pipe(v.string(), v.email("Invalid email address")),
    role: v.picklist(["student", "teacher", "admin"]),
    invite_code: v.optional(v.string()),
    password: v.pipe(v.string(), v.minLength(8, "Password must be at least 8 characters")),
    confirmPassword: v.pipe(v.string(), v.minLength(1, "Please confirm your password")),
  }),
  v.forward(
    v.check((data) => data.password === data.confirmPassword, "Passwords do not match"),
    ["confirmPassword"]
  ),
  v.forward(
    v.check((data) => {
      if (["teacher", "admin"].includes(data.role) && !data.invite_code) {
        return false
      }
      return true
    }, "Invite code is required for this role"),
    ["invite_code"]
  )
)

export type RegisterValues = v.InferInput<typeof registerSchema>

export const resetPasswordSchema = v.object({
  email: v.pipe(v.string(), v.email("auth:messages.invalidEmail")),
})

export type ResetPasswordValues = v.InferInput<typeof resetPasswordSchema>

export const newPasswordSchema = v.pipe(
  v.object({
    password: v.pipe(v.string(), v.minLength(8, "Password must be at least 8 characters")),
    confirmPassword: v.pipe(v.string(), v.minLength(1, "Please confirm your password")),
  }),
  v.forward(
    v.check((data) => data.password === data.confirmPassword, "Passwords do not match"),
    ["confirmPassword"]
  )
)

export type NewPasswordValues = v.InferInput<typeof newPasswordSchema>
