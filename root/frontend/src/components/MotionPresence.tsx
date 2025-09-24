import type { ComponentProps } from "react";
import { AnimatePresence } from "framer-motion";

export default function MotionPresence({
  children,
  ...props
}: ComponentProps<typeof AnimatePresence>) {
  return (
    <AnimatePresence initial={false} mode="wait" {...props}>
      {children}
    </AnimatePresence>
  );
}