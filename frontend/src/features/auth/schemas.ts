import * as v from "valibot"

export const loginSchema = v.object({
  email: v.pipe(
    v.string(),
    v.minLength(1, "auth:messages.emailRequired"),
    v.email("auth:messages.invalidEmail")
  ),
  password: v.pipe(v.string(), v.minLength(1, "auth:messages.passwordRequired")),
  rememberEmail: v.optional(v.boolean()),
  trustDevice: v.optional(v.boolean()),
})

export type LoginValues = v.InferInput<typeof loginSchema>

export const registerSchema = v.pipe(
  v.object({
    full_name: v.pipe(v.string(), v.minLength(2, "auth:validation.nameMinLength")),
    email: v.pipe(v.string(), v.email("auth:validation.emailInvalid")),
    role: v.picklist(["student", "teacher", "admin"]),
    invite_code: v.optional(v.string()),
    password: v.pipe(v.string(), v.minLength(8, "auth:validation.passwordMinLength")),
    confirmPassword: v.pipe(v.string(), v.minLength(1, "auth:validation.confirmPasswordRequired")),
  }),
  v.forward(
    v.check((data) => data.password === data.confirmPassword, "auth:validation.passwordsMismatch"),
    ["confirmPassword"]
  ),
  v.forward(
    v.check((data) => {
      if (["teacher", "admin"].includes(data.role) && !data.invite_code) {
        return false
      }
      return true
    }, "auth:validation.inviteCodeRequired"),
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
    password: v.pipe(v.string(), v.minLength(8, "auth:validation.passwordMinLength")),
    confirmPassword: v.pipe(v.string(), v.minLength(1, "auth:validation.confirmPasswordRequired")),
  }),
  v.forward(
    v.check((data) => data.password === data.confirmPassword, "auth:validation.passwordsMismatch"),
    ["confirmPassword"]
  )
)

export type NewPasswordValues = v.InferInput<typeof newPasswordSchema>
