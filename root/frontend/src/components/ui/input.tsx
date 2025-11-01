import {
  forwardRef,
  useId,
  type InputHTMLAttributes,
  type ReactNode,
  type TextareaHTMLAttributes,
} from "react"
import { cn } from "@/utils/cn"

type SharedFieldProps = {
  label?: ReactNode
  helperText?: ReactNode
  errorText?: ReactNode
  successText?: ReactNode
  leadingIcon?: ReactNode
  trailingIcon?: ReactNode
  invalid?: boolean
  valid?: boolean
  loading?: boolean
  requiredIndicator?: ReactNode
  className?: string
  inputClassName?: string
}

const buildFieldStateClasses = (invalid?: boolean, valid?: boolean) => {
  if (invalid) {
    return "border-[color:var(--ue-form-error-border,rgba(220,38,38,0.58))] shadow-[0_0_0_1px_rgba(220,38,38,0.2)]"
  }
  if (valid) {
    return "border-[color:var(--ue-form-success-border,rgba(34,197,94,0.55))] shadow-[0_0_0_1px_rgba(34,197,94,0.18)]"
  }
  return "border-[color:var(--glass-border)] shadow-[0_18px_48px_rgba(15,23,42,0.08)]"
}

const Spinner = () => (
  <span className="h-4 w-4 animate-spin rounded-full border-2 border-[color:rgba(148,163,184,0.35)] border-t-[color:var(--nav-link)]" />
)

type TextInputProps = InputHTMLAttributes<HTMLInputElement> & SharedFieldProps

export const TextInput = forwardRef<HTMLInputElement, TextInputProps>(
  (
    {
      id: idProp,
      label,
      helperText,
      errorText,
      successText,
      leadingIcon,
      trailingIcon,
      invalid = false,
      valid = false,
      loading = false,
      requiredIndicator = <span className="text-[color:var(--badge-lab)]">*</span>,
      className,
      inputClassName,
      disabled,
      ...rest
    },
    ref
  ) => {
    const generatedId = useId()
    const id = idProp ?? generatedId
    const helperId = helperText ? `${id}-helper` : undefined
    const errorId = errorText ? `${id}-error` : undefined
    const successId = successText ? `${id}-success` : undefined
    const describedBy = [helperId, errorId, successId].filter(Boolean).join(" ") || undefined
    const isInvalid = invalid || Boolean(errorText)
    const isValid = valid && !isInvalid

    return (
      <div className={cn("flex flex-col gap-2", className)}>
        {label ? (
          <label
            htmlFor={id}
            className="flex items-center gap-1 text-sm font-medium text-[color:var(--secondary-text)]"
          >
            <span>{label}</span>
            {rest.required ? requiredIndicator : null}
          </label>
        ) : null}
        <div
          className={cn(
            "relative flex items-center gap-3 rounded-[var(--ue-radius-lg,1rem)] bg-[color:var(--card-bg)]/96 px-4",
            "transition-[box-shadow,border-color] duration-200 ease-out",
            !isInvalid &&
              "focus-within:border-[color:var(--nav-link)] focus-within:shadow-[var(--ue-focus-ring)]",
            buildFieldStateClasses(isInvalid, isValid),
            disabled && "opacity-70"
          )}
        >
          {leadingIcon ? (
            <span className="inline-flex items-center text-[color:var(--secondary-text)]">
              {leadingIcon}
            </span>
          ) : null}
          <input
            ref={ref}
            id={id}
            className={cn(
              "flex-1 border-none bg-transparent py-3 text-[color:var(--page-text)] placeholder:text-[color:var(--placeholder-fg)] focus:outline-none",
              inputClassName
            )}
            aria-invalid={isInvalid ? "true" : undefined}
            aria-describedby={describedBy}
            disabled={disabled}
            {...rest}
          />
          {loading || trailingIcon ? (
            <span className="flex items-center gap-2 text-[color:var(--secondary-text)]">
              {loading ? <Spinner /> : trailingIcon}
            </span>
          ) : null}
        </div>
        {helperText ? (
          <p id={helperId} className="text-xs text-[color:var(--secondary-text)]">
            {helperText}
          </p>
        ) : null}
        {errorText ? (
          <p id={errorId} className="text-xs text-[color:var(--badge-lab)]">
            {errorText}
          </p>
        ) : null}
        {!errorText && successText ? (
          <p id={successId} className="text-xs text-[color:var(--badge-prac)]">
            {successText}
          </p>
        ) : null}
      </div>
    )
  }
)

TextInput.displayName = "TextInput"

type TextAreaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & SharedFieldProps

export const TextArea = forwardRef<HTMLTextAreaElement, TextAreaProps>(
  (
    {
      id: idProp,
      label,
      helperText,
      errorText,
      successText,
      leadingIcon,
      trailingIcon,
      invalid = false,
      valid = false,
      loading = false,
      requiredIndicator = <span className="text-[color:var(--badge-lab)]">*</span>,
      className,
      inputClassName,
      disabled,
      rows = 4,
      ...rest
    },
    ref
  ) => {
    const generatedId = useId()
    const id = idProp ?? generatedId
    const helperId = helperText ? `${id}-helper` : undefined
    const errorId = errorText ? `${id}-error` : undefined
    const successId = successText ? `${id}-success` : undefined
    const describedBy = [helperId, errorId, successId].filter(Boolean).join(" ") || undefined
    const isInvalid = invalid || Boolean(errorText)
    const isValid = valid && !isInvalid

    return (
      <div className={cn("flex flex-col gap-2", className)}>
        {label ? (
          <label
            htmlFor={id}
            className="flex items-center gap-1 text-sm font-medium text-[color:var(--secondary-text)]"
          >
            <span>{label}</span>
            {rest.required ? requiredIndicator : null}
          </label>
        ) : null}
        <div
          className={cn(
            "relative flex items-start gap-3 rounded-[var(--ue-radius-lg,1rem)] bg-[color:var(--card-bg)]/96 px-4",
            "transition-[box-shadow,border-color] duration-200 ease-out",
            !isInvalid &&
              "focus-within:border-[color:var(--nav-link)] focus-within:shadow-[var(--ue-focus-ring)]",
            buildFieldStateClasses(isInvalid, isValid),
            disabled && "opacity-70"
          )}
        >
          {leadingIcon ? (
            <span className="mt-3 inline-flex items-start text-[color:var(--secondary-text)]">
              {leadingIcon}
            </span>
          ) : null}
          <textarea
            ref={ref}
            id={id}
            rows={rows}
            className={cn(
              "flex-1 resize-y border-none bg-transparent py-3 text-[color:var(--page-text)] placeholder:text-[color:var(--placeholder-fg)] focus:outline-none",
              "scrollbar-thin scrollbar-track-transparent scrollbar-thumb-[color:rgba(148,163,184,0.4)]",
              inputClassName
            )}
            aria-invalid={isInvalid ? "true" : undefined}
            aria-describedby={describedBy}
            disabled={disabled}
            {...rest}
          />
          {loading || trailingIcon ? (
            <span className="mt-3 flex items-start text-[color:var(--secondary-text)]">
              {loading ? <Spinner /> : trailingIcon}
            </span>
          ) : null}
        </div>
        {helperText ? (
          <p id={helperId} className="text-xs text-[color:var(--secondary-text)]">
            {helperText}
          </p>
        ) : null}
        {errorText ? (
          <p id={errorId} className="text-xs text-[color:var(--badge-lab)]">
            {errorText}
          </p>
        ) : null}
        {!errorText && successText ? (
          <p id={successId} className="text-xs text-[color:var(--badge-prac)]">
            {successText}
          </p>
        ) : null}
      </div>
    )
  }
)

TextArea.displayName = "TextArea"
