"use client"

import * as React from "react"
import { motion, AnimatePresence } from "framer-motion"
import { ChevronDown } from "lucide-react"
import { cn } from "@/utils/cn"

interface SelectOption {
  value: string
  label: string
}

interface SelectProps {
  value?: string
  onValueChange?: (value: string) => void
  options: SelectOption[]
  placeholder?: string
  className?: string
  disabled?: boolean
  error?: boolean
}

const Select = ({
  value,
  onValueChange,
  options,
  placeholder = "Select an option...",
  className,
  disabled,
  error,
}: SelectProps) => {
  const [isOpen, setIsOpen] = React.useState(false)
  const containerRef = React.useRef<HTMLDivElement>(null)

  const selectedOption = options.find((opt) => opt.value === value)

  React.useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [])

  return (
    <div ref={containerRef} className={cn("relative w-full", className)}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          "flex min-h-12 w-full items-center justify-between gap-2 rounded-xl border-2 px-4 py-2 text-left transition-all duration-300",
          "border-border-strong bg-surface/40 backdrop-blur-md shadow-sm",
          "hover:border-brand/40 hover:bg-surface-hover/60",
          "focus:outline-none focus:ring-4 focus:ring-brand/10",
          isOpen &&
            "border-brand ring-4 ring-brand/10 shadow-[0_0_12px_rgba(var(--primary-main),0.1)]",
          error && "border-error bg-error/5 focus:ring-error/10",
          disabled && "cursor-not-allowed opacity-50 grayscale",
          !selectedOption && "text-tertiary-text"
        )}
      >
        <span className="truncate">{selectedOption ? selectedOption.label : placeholder}</span>
        <ChevronDown
          className={cn(
            "h-4 w-4 shrink-0 text-secondary-text transition-transform duration-300",
            isOpen && "rotate-180"
          )}
        />
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: -10, scale: 0.98 }}
            animate={{ opacity: 1, y: 4, scale: 1 }}
            exit={{ opacity: 0, y: -10, scale: 0.98 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className={cn(
              "absolute z-(--ue-z-index-dropdown,50) mt-1 w-full overflow-hidden rounded-xl border border-glass-border bg-surface/90 shadow-glass backdrop-blur-xl",
              "p-1.5"
            )}
          >
            <div className="max-h-60 overflow-y-auto scrollbar-thin scrollbar-thumb-brand/20">
              {options.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => {
                    onValueChange?.(option.value)
                    setIsOpen(false)
                  }}
                  className={cn(
                    "flex w-full items-center rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-200",
                    "hover:bg-brand/10 hover:text-brand",
                    value === option.value
                      ? "bg-brand text-inverse-text shadow-sm"
                      : "text-primary-text"
                  )}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export { Select }
export type { SelectOption }
