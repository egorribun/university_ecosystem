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

const noopValueChange = (_value: string): void => undefined

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
  // `undefined` is the explicit no-active-option sentinel.  Keeping that
  // state separate from a valid array index prevents closed comboboxes from
  // ever exposing a synthetic option id to assistive technology.
  const [activeIndex, setActiveIndex] = React.useState<number>()
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
    if (!isOpen) return

    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [isOpen])

  // Scroll active option into view
  React.useEffect(() => {
    if (!isOpen || activeIndex === undefined) return
    const optionElement = document.getElementById(computeOptionId(activeIndex))
    optionElement?.scrollIntoView({ block: "nearest" })
  }, [activeIndex, isOpen, computeOptionId])

  const openListbox = React.useCallback(() => {
    setIsOpen(true)
    // Focus the selected or first option when opening
    setActiveIndex(selectedIndex === -1 ? (options.length > 0 ? 0 : undefined) : selectedIndex)
  }, [options.length, selectedIndex])

  const closeListbox = () => {
    setIsOpen(false)
  }

  const selectOption = (index: number | undefined) => {
    if (index === undefined) {
      closeListbox()
      return
    }
    const option = options[index]
    const optionValue = option && option.value
    if (!option) return
    const notifyValueChange = onValueChange ?? noopValueChange
    notifyValueChange(optionValue as string)
    closeListbox()
  }

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

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (disabled) return

    switch (event.key) {
      case "Enter":
      case " ": {
        event.preventDefault()
        if (!isOpen) {
          openListbox()
          break
        }
        selectOption(activeIndex)
        break
      }
      case "ArrowDown": {
        event.preventDefault()
        if (!isOpen) {
          openListbox()
        } else {
          setActiveIndex((previous) =>
            previous === undefined
              ? options.length > 0
                ? 0
                : undefined
              : Math.min(previous + 1, options.length - 1)
          )
        }
        break
      }
      case "ArrowUp": {
        event.preventDefault()
        if (!isOpen) {
          openListbox()
        } else {
          setActiveIndex((previous) =>
            previous === undefined
              ? options.length > 0
                ? 0
                : undefined
              : Math.max(previous - 1, 0)
          )
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
        closeListbox()
        break
      }
      default: {
        if (event.key.length === 1 && !event.ctrlKey && !event.metaKey) {
          handleTypeAhead(event.key)
        }
      }
    }
  }

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
          isOpen && activeIndex !== undefined ? computeOptionId(activeIndex) : undefined
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
                      "flex min-h-11 w-full cursor-pointer items-center rounded-lg px-3 py-2.5 text-sm font-medium transition-colors duration-fast",
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
