import * as React from "react"
import { cn } from "@/utils/cn"

function TableImpl(
  { className, ...props }: React.HTMLAttributes<HTMLTableElement>,
  ref: React.ForwardedRef<HTMLTableElement>
) {
  return (
    <div className="relative w-full overflow-auto">
      <table ref={ref} className={cn("w-full caption-bottom text-sm", className)} {...props} />
    </div>
  )
}
const Table = React.forwardRef<HTMLTableElement, React.HTMLAttributes<HTMLTableElement>>(TableImpl)

function TableHeaderImpl(
  { className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>,
  ref: React.ForwardedRef<HTMLTableSectionElement>
) {
  return <thead ref={ref} className={cn("[&_tr]:border-b", className)} {...props} />
}
const TableHeader = React.forwardRef<
  HTMLTableSectionElement,
  React.HTMLAttributes<HTMLTableSectionElement>
>(TableHeaderImpl)

function TableBodyImpl(
  { className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>,
  ref: React.ForwardedRef<HTMLTableSectionElement>
) {
  return <tbody ref={ref} className={cn("[&_tr:last-child]:border-0", className)} {...props} />
}
const TableBody = React.forwardRef<
  HTMLTableSectionElement,
  React.HTMLAttributes<HTMLTableSectionElement>
>(TableBodyImpl)

function TableFooterImpl(
  { className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>,
  ref: React.ForwardedRef<HTMLTableSectionElement>
) {
  return (
    <tfoot
      ref={ref}
      className={cn("border-t bg-surface/50 font-medium [&>tr]:last:border-b-0", className)}
      {...props}
    />
  )
}
const TableFooter = React.forwardRef<
  HTMLTableSectionElement,
  React.HTMLAttributes<HTMLTableSectionElement>
>(TableFooterImpl)

function TableRowImpl(
  { className, ...props }: React.HTMLAttributes<HTMLTableRowElement>,
  ref: React.ForwardedRef<HTMLTableRowElement>
) {
  return (
    <tr
      ref={ref}
      className={cn(
        "border-b transition-colors hover:bg-surface-hover/50 data-[state=selected]:bg-surface-selected",
        className
      )}
      {...props}
    />
  )
}
const TableRow = React.forwardRef<HTMLTableRowElement, React.HTMLAttributes<HTMLTableRowElement>>(
  TableRowImpl
)

function TableHeadImpl(
  { className, ...props }: React.ThHTMLAttributes<HTMLTableCellElement>,
  ref: React.ForwardedRef<HTMLTableCellElement>
) {
  return (
    <th
      ref={ref}
      className={cn(
        "h-10 px-2 text-left align-middle font-medium text-text-secondary [&:has([role=checkbox])]:pr-0",
        className
      )}
      {...props}
    />
  )
}
const TableHead = React.forwardRef<
  HTMLTableCellElement,
  React.ThHTMLAttributes<HTMLTableCellElement>
>(TableHeadImpl)

function TableCellImpl(
  { className, ...props }: React.TdHTMLAttributes<HTMLTableCellElement>,
  ref: React.ForwardedRef<HTMLTableCellElement>
) {
  return (
    <td
      ref={ref}
      className={cn("p-2 align-middle [&:has([role=checkbox])]:pr-0", className)}
      {...props}
    />
  )
}
const TableCell = React.forwardRef<
  HTMLTableCellElement,
  React.TdHTMLAttributes<HTMLTableCellElement>
>(TableCellImpl)

function TableCaptionImpl(
  { className, ...props }: React.HTMLAttributes<HTMLTableCaptionElement>,
  ref: React.ForwardedRef<HTMLTableCaptionElement>
) {
  return (
    <caption ref={ref} className={cn("mt-4 text-sm text-text-tertiary", className)} {...props} />
  )
}
const TableCaption = React.forwardRef<
  HTMLTableCaptionElement,
  React.HTMLAttributes<HTMLTableCaptionElement>
>(TableCaptionImpl)

export { Table, TableHeader, TableBody, TableFooter, TableHead, TableRow, TableCell, TableCaption }
