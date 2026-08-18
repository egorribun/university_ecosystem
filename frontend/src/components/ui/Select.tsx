import * as React from "react"
import { m, AnimatePresence } from "framer-motion"
import { ChevronDown } from "lucide-react"
import { useTranslation } from "react-i18next"
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
  /** Unique identifier for ARIA id generation */
  id?: string
  /** Accessible label for screen readers */
  "aria-label"?: string
  "aria-labelledby"?: string
}

/**
 * Accessible Select component following WAI-ARIA Listbox pattern.
 *
 * Keyboard navigation:
 *  - Enter/Space → open/close + select
 *  - ArrowDown/Up → navigate options
 *  - Home/End → jump to first/last
 *  - Escape → close
 *  - Type-ahead → focus matching option
 */
const Select = ({
  value,
  onValueChange,
  options,
  placeholder,
  className,
  disabled,
  error,
  id: externalId,
  "aria-label": ariaLabel,
  "aria-labelledby": ariaLabelledBy,
}: SelectProps) => {
  const { t } = useTranslation("common")
  const defaultPlaceholder = placeholder ?? t("select.placeholder")
  const generatedId = React.useId()
  const baseId = externalId ?? generatedId

  const [isOpen, setIsOpen] = React.useState(false)
  const [activeIndex, setActiveIndex] = React.useState(-1)
  const containerRef = React.useRef<HTMLDivElement>(null)
  const listboxRef = React.useRef<HTMLDivElement>(null)
  const typeAheadBuffer = React.useRef("")
  const typeAheadTimer = React.useRef<ReturnType<typeof setTimeout>>(undefined)

  const selectedOption = options.find((option) => option.value === value)
  const selectedIndex = options.findIndex((option) => option.value === value)

  const triggerButtonId = `${baseId}-trigger`
  const listboxId = `${baseId}-listbox`
  const computeOptionId = React.useCallback(
    (index: number) => `${baseId}-option-${index}`,
    [baseId]
  )

  // Close on outside click
  React.useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [])

  // Scroll active option into view
  React.useEffect(() => {
    if (!isOpen || activeIndex < 0) return
    const optionElement = document.getElementById(computeOptionId(activeIndex))
    optionElement?.scrollIntoView({ block: "nearest" })
  }, [activeIndex, isOpen, computeOptionId])

  const openListbox = React.useCallback(() => {
    setIsOpen(true)
    // Focus the selected or first option when opening
    setActiveIndex(selectedIndex >= 0 ? selectedIndex : 0)
  }, [selectedIndex])

  const closeListbox = React.useCallback(() => {
    setIsOpen(false)
    setActiveIndex(-1)
  }, [])

  const selectOption = React.useCallback(
    (index: number) => {
      const option = options[index]
      if (!option) return
      onValueChange?.(option.value)
      closeListbox()
    },
    [options, onValueChange, closeListbox]
  )

  // Type-ahead: typing a character focuses the first matching option
  const handleTypeAhead = React.useCallback(
    (character: string) => {
      if (!isOpen) return

      clearTimeout(typeAheadTimer.current)
      typeAheadBuffer.current += character.toLowerCase()

      const matchIndex = options.findIndex((option) =>
        option.label.toLowerCase().startsWith(typeAheadBuffer.current)
      )
      if (matchIndex >= 0) {
        setActiveIndex(matchIndex)
      }

      typeAheadTimer.current = setTimeout(() => {
        typeAheadBuffer.current = ""
      }, 500)
    },
    [isOpen, options]
  )

  const handleKeyDown = React.useCallback(
    (event: React.KeyboardEvent) => {
      if (disabled) return

      switch (event.key) {
        case "Enter":
        case " ": {
          event.preventDefault()
          if (isOpen && activeIndex >= 0) {
            selectOption(activeIndex)
          } else {
            openListbox()
          }
          break
        }
        case "ArrowDown": {
          event.preventDefault()
          if (!isOpen) {
            openListbox()
          } else {
            setActiveIndex((previous) => Math.min(previous + 1, options.length - 1))
          }
          break
        }
        case "ArrowUp": {
          event.preventDefault()
          if (!isOpen) {
            openListbox()
          } else {
            setActiveIndex((previous) => Math.max(previous - 1, 0))
          }
          break
        }
        case "Home": {
          if (isOpen) {
            event.preventDefault()
            setActiveIndex(0)
          }
          break
        }
        case "End": {
          if (isOpen) {
            event.preventDefault()
            setActiveIndex(options.length - 1)
          }
          break
        }
        case "Escape": {
          if (isOpen) {
            event.preventDefault()
            closeListbox()
          }
          break
        }
        case "Tab": {
          if (isOpen) {
            closeListbox()
          }
          break
        }
        default: {
          if (event.key.length === 1 && !event.ctrlKey && !event.metaKey) {
            handleTypeAhead(event.key)
          }
        }
      }
    },
    [
      disabled,
      isOpen,
      activeIndex,
      options.length,
      openListbox,
      closeListbox,
      selectOption,
      handleTypeAhead,
    ]
  )

  return (
    <div ref={containerRef} className={cn("relative w-full", className)}>
      <button
        id={triggerButtonId}
        type="button"
        role="combobox"
        aria-expanded={isOpen}
        aria-haspopup="listbox"
        aria-controls={listboxId}
        aria-activedescendant={
          isOpen && activeIndex >= 0 ? computeOptionId(activeIndex) : undefined
        }
        aria-label={ariaLabel}
        aria-labelledby={ariaLabelledBy}
        disabled={disabled}
        onClick={() => (isOpen ? closeListbox() : openListbox())}
        onKeyDown={handleKeyDown}
        className={cn(
          "flex min-h-12 w-full items-center justify-between gap-2 rounded-xl border-2 px-4 py-2 text-left transition-colors duration-base",
          "border-glass-border bg-glass-bg backdrop-blur-glass shadow-glass",
          "hover:border-brand/(--opacity-medium) hover:bg-glass-tint1",
          "focus:outline-none focus:ring-4 focus:ring-brand/(--opacity-subtle)",
          isOpen && "border-brand ring-4 ring-brand/(--opacity-subtle) shadow-glow-primary",
          error && "border-error-text bg-error-bg focus:ring-error-text/(--opacity-subtle)",
          disabled && "cursor-not-allowed opacity-medium grayscale",
          !selectedOption && "text-text-tertiary"
        )}
      >
        <span className="truncate">
          {selectedOption ? selectedOption.label : defaultPlaceholder}
        </span>
        <ChevronDown
          className={cn(
            "h-4 w-4 shrink-0 text-text-secondary transition-transform duration-base",
            isOpen && "rotate-180"
          )}
          aria-hidden="true"
        />
      </button>

      <AnimatePresence>
        {isOpen && (
          <m.div
            ref={listboxRef}
            role="listbox"
            id={listboxId}
            aria-label={ariaLabel}
            tabIndex={-1}
            initial={{ opacity: 0, y: -10, scale: 0.98 }}
            animate={{ opacity: 1, y: 4, scale: 1 }}
            exit={{ opacity: 0, y: -10, scale: 0.98 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className={cn(
              "absolute z-dropdown mt-1 w-full overflow-hidden rounded-xl border border-glass-border-subtle bg-glass-elevated shadow-lg backdrop-blur-xl",
              "p-1.5"
            )}
          >
            <div className="max-h-60 overflow-y-auto scrollbar-thin scrollbar-thumb-brand/(--opacity-dim)">
              {options.map((option, index) => {
                const isSelected = value === option.value
                const isActive = index === activeIndex

                return (
                  <div
                    key={option.value}
                    id={computeOptionId(index)}
                    role="option"
                    aria-selected={isSelected}
                    tabIndex={-1}
                    onMouseEnter={() => setActiveIndex(index)}
                    onMouseDown={(event) => {
                      // Prevent blur on the trigger button
                      event.preventDefault()
                      selectOption(index)
                    }}
                    className={cn(
                      "flex w-full cursor-pointer items-center rounded-lg px-3 py-2.5 text-sm font-medium transition-colors duration-fast",
                      isSelected
                        ? "bg-brand text-inverse-text shadow-sm"
                        : isActive
                          ? "bg-brand/(--opacity-subtle) text-brand"
                          : "text-text-primary hover:bg-brand/(--opacity-subtle) hover:text-brand"
                    )}
                  >
                    {option.label}
                  </div>
                )
              })}
            </div>
          </m.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export { Select }
export type { SelectOption, SelectProps }
