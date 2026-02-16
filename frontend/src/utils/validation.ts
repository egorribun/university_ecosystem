import { z } from "zod"

/**
 * Shared validation schemas for authentication forms.
 * Using Zod allows for type inference and easy integration with React Hook Form.
 */

// Email regex matching the simple one used across the app
// We use regex instead of z.email() to match existing loose validation if needed
// but z.email() is generally preferred for standard apps.
// For now, let's allow z.string().email() as a baseline.
export const loginSchema = z.object({
  username: z
    .string()
    .min(1, { message: "auth:messages.emailRequired" })
    .email({ message: "auth:messages.invalidEmail" }),
  password: z.string().min(1, { message: "auth:messages.passwordRequired" }),
  trustDevice: z.boolean(),
})

export type LoginFormValues = z.infer<typeof loginSchema>
