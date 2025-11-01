import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useState,
  type ComponentPropsWithoutRef,
  type HTMLAttributes,
  type MouseEventHandler,
  type MutableRefObject,
  type PropsWithChildren,
} from "react"
import { createPortal } from "react-dom"
import { cn } from "@/utils/cn"
import useFocusTrap from "@/hooks/useFocusTrap"

type ModalContextValue = {
  close: () => void
  registerLabel: (id: string | undefined) => void
  registerDescription: (id: string | undefined) => void
  labelledBy?: string
  describedBy?: string
  trapRef: MutableRefObject<HTMLDivElement | null>
}

const ModalContext = createContext<ModalContextValue | null>(null)

const isBrowser = typeof document !== "undefined"

const getPortalRoot = (container?: HTMLElement | null) => {
  if (container) return container
  if (!isBrowser) return null
  const existing = document.getElementById("ue-modal-root")
  if (existing) return existing
  const node = document.createElement("div")
  node.setAttribute("id", "ue-modal-root")
  document.body.appendChild(node)
  return node
}

export interface ModalProps extends PropsWithChildren {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Optional element to portal into; defaults to body. */
  container?: HTMLElement | null
  /** Click on the scrim closes the modal when true. */
  closeOnOverlayClick?: boolean
  /** Disable escape key closing when false. */
  closeOnEscape?: boolean
  /** Optional className applied to overlay wrapper. */
  className?: string
  /** Additional className for the overlay element. */
  overlayClassName?: string
  /** Optional initial focus target for the focus trap. */
  initialFocus?: Parameters<typeof useFocusTrap>[0]["initialFocus"]
  /** Optional fallback focus target for the focus trap. */
  fallbackFocus?: Parameters<typeof useFocusTrap>[0]["fallbackFocus"]
  /** Whether focus should return to the trigger when the dialog closes. */
  returnFocus?: boolean
}

export function Modal({
  open,
  onOpenChange,
  children,
  container,
  closeOnOverlayClick = true,
  closeOnEscape = true,
  className,
  overlayClassName,
  initialFocus,
  fallbackFocus,
  returnFocus = true,
}: ModalProps) {
  const [labelledBy, setLabelledBy] = useState<string | undefined>()
  const [describedBy, setDescribedBy] = useState<string | undefined>()

  const trapRef = useFocusTrap<HTMLDivElement>({
    active: open,
    initialFocus,
    fallbackFocus,
    returnFocus,
    onDeactivate: () => {
      onOpenChange(false)
    },
  })

  useEffect(() => {
    if (!open || !closeOnEscape) return undefined
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault()
        onOpenChange(false)
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [open, closeOnEscape, onOpenChange])

  useEffect(() => {
    if (!open) return undefined
    if (!isBrowser) return undefined
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = "hidden"
    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [open])

  const close = useCallback(() => onOpenChange(false), [onOpenChange])

  const contextValue = useMemo<ModalContextValue>(
    () => ({
      close,
      registerLabel: setLabelledBy,
      registerDescription: setDescribedBy,
      labelledBy,
      describedBy,
      trapRef,
    }),
    [close, labelledBy, describedBy, trapRef]
  )

  const portalNode = getPortalRoot(container)
  if (!open || !portalNode) return null

  return createPortal(
    <ModalContext.Provider value={contextValue}>
      <div
        className={cn(
          "fixed inset-0 flex items-center justify-center p-4 sm:p-8",
          className
        )}
        style={{ zIndex: "var(--ue-z-index-overlay)" }}
      >
        <div
          data-testid="modal-overlay"
          aria-hidden
          className={cn(
            "absolute inset-0 bg-[color:var(--ue-overlay-scrim,rgba(8,11,21,0.42))] backdrop-blur-xl",
            overlayClassName
          )}
          onClick={closeOnOverlayClick ? close : undefined}
        />
        {children}
      </div>
    </ModalContext.Provider>,
    portalNode
  )
}

const useModalContext = () => {
  const context = useContext(ModalContext)
  if (!context) {
    throw new Error("Modal components must be used within a <Modal />")
  }
  return context
}

export interface ModalContentProps extends HTMLAttributes<HTMLDivElement> {
  /** Visually hides scrollbars on the dialog container. */
  hideScrollbars?: boolean
}

export function ModalContent({ hideScrollbars = false, className, children, ...rest }: ModalContentProps) {
  const { labelledBy, describedBy, trapRef } = useModalContext()

  return (
    <div
      ref={trapRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby={labelledBy}
      aria-describedby={describedBy}
      className={cn(
        "relative z-[1] flex w-full max-w-2xl flex-col gap-6 overflow-hidden rounded-[min(1.5rem,calc(var(--ue-radius-lg,1rem)*1.1))]",
        "max-h-[min(85vh,720px)]",
        "border border-[color:var(--glass-border)] bg-[color:var(--card-bg)]/98 text-[color:var(--page-text)]",
        "shadow-[0_40px_120px_rgba(15,23,42,0.38)]",
        "focus-visible:outline-none focus-visible:shadow-[var(--ue-focus-ring)]",
        hideScrollbars && "[scrollbar-width:none] [&::-webkit-scrollbar]:hidden",
        className
      )}
      tabIndex={-1}
      {...rest}
    >
      {children}
    </div>
  )
}

export function ModalHeader({ className, children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "flex flex-col gap-2 border-b border-[color:var(--glass-border)]/70 bg-[color:var(--card-bg)]/82 px-6 py-5",
        className
      )}
      {...rest}
    >
      {children}
    </div>
  )
}

export function ModalTitle({ className, children, ...rest }: ComponentPropsWithoutRef<"h2">) {
  const { registerLabel } = useModalContext()
  const titleId = useId()

  useEffect(() => {
    registerLabel(titleId)
    return () => registerLabel(undefined)
  }, [registerLabel, titleId])

  return (
    <h2
      id={titleId}
      className={cn("text-2xl font-semibold tracking-tight text-[color:var(--page-text)]", className)}
      {...rest}
    >
      {children}
    </h2>
  )
}

export function ModalDescription({ className, children, ...rest }: ComponentPropsWithoutRef<"p">) {
  const { registerDescription } = useModalContext()
  const descriptionId = useId()

  useEffect(() => {
    registerDescription(descriptionId)
    return () => registerDescription(undefined)
  }, [registerDescription, descriptionId])

  return (
    <p
      id={descriptionId}
      className={cn("text-base leading-relaxed text-[color:var(--secondary-text)]", className)}
      {...rest}
    >
      {children}
    </p>
  )
}

export function ModalBody({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "flex flex-1 flex-col gap-4 overflow-y-auto px-6 py-5",
        "[scrollbar-width:thin] [&::-webkit-scrollbar]:h-2 [&::-webkit-scrollbar]:w-2",
        className
      )}
      {...rest}
    />
  )
}

export function ModalFooter({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "flex flex-col-reverse gap-3 border-t border-[color:var(--glass-border)]/70 bg-[color:var(--card-bg)]/82 px-6 py-5 sm:flex-row sm:justify-end",
        className
      )}
      {...rest}
    />
  )
}

export function ModalCloseButton({
  children = "Close",
  className,
  ...rest
}: ComponentPropsWithoutRef<"button">) {
  const { close } = useModalContext()
  const handleClick = useCallback<MouseEventHandler<HTMLButtonElement>>(
    (event) => {
      rest.onClick?.(event)
      if (event.defaultPrevented) return
      close()
    },
    [close, rest]
  )

  return (
    <button
      type="button"
      className={cn(
        "inline-flex items-center justify-center gap-2 self-start rounded-full border border-[color:var(--glass-border)] bg-[color:var(--card-bg)] px-4 py-2 text-sm font-semibold text-[color:var(--nav-link)] transition-colors",
        "hover:bg-[color:var(--menu-hover-bg)] hover:text-[color:var(--menu-hover-text)]",
        "focus-visible:outline-none focus-visible:shadow-[var(--ue-focus-ring)]",
        className
      )}
      onClick={handleClick}
      {...rest}
    >
      {children}
    </button>
  )
}

Modal.displayName = "Modal"
ModalContent.displayName = "ModalContent"
ModalHeader.displayName = "ModalHeader"
ModalTitle.displayName = "ModalTitle"
ModalDescription.displayName = "ModalDescription"
ModalBody.displayName = "ModalBody"
ModalFooter.displayName = "ModalFooter"
ModalCloseButton.displayName = "ModalCloseButton"

