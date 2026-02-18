import { z } from "zod"

export const loginSchema = z.object({
  email: z.string().min(1, "Email is required").email("Invalid email address"),
  password: z.string().min(1, "Password is required"),
  trustDevice: z.boolean().optional(),
})

export type LoginValues = z.infer<typeof loginSchema>

export const registerSchema = z
  .object({
    full_name: z.string().min(2, "Name must be at least 2 characters"),
    email: z.string().email("Invalid email address"),
    role: z.enum(["student", "teacher", "admin"]),
    invite_code: z.string().optional(),
    password: z.string().min(8, "Password must be at least 8 characters"),
    confirmPassword: z.string().min(1, "Please confirm your password"),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "Passwords do not match",
    path: ["confirmPassword"],
  })
  .superRefine((data, ctx) => {
    if (["teacher", "admin"].includes(data.role) && !data.invite_code) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Invite code is required for this role",
        path: ["invite_code"],
      })
    }
  })

export type RegisterValues = z.infer<typeof registerSchema>

export const resetPasswordSchema = z.object({
  email: z.string().email("Invalid email address"),
})

export type ResetPasswordValues = z.infer<typeof resetPasswordSchema>

export const newPasswordSchema = z
  .object({
    password: z.string().min(8, "Password must be at least 8 characters"),
    confirmPassword: z.string().min(1, "Please confirm your password"),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "Passwords do not match",
    path: ["confirmPassword"],
  })

export type NewPasswordValues = z.infer<typeof newPasswordSchema>
