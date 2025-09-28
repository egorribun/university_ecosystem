import * as React from "react";

import { cn } from "@/utils/cn";

const badgeVariants = {
  default:
    "inline-flex items-center rounded-full border border-transparent bg-sky-600 px-2.5 py-0.5 text-xs font-medium text-white shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 dark:bg-sky-500", 
  secondary:
    "inline-flex items-center rounded-full border border-transparent bg-slate-200 px-2.5 py-0.5 text-xs font-medium text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 dark:bg-slate-700 dark:text-slate-100", 
  outline:
    "inline-flex items-center rounded-full border border-slate-300 px-2.5 py-0.5 text-xs font-medium text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 dark:border-slate-600 dark:text-slate-200",
} as const;

export type BadgeVariant = keyof typeof badgeVariants;

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: BadgeVariant;
}

export const Badge = ({ className, variant = "default", ...props }: BadgeProps) => (
  <div className={cn(badgeVariants[variant], className)} {...props} />
);

Badge.displayName = "Badge";
