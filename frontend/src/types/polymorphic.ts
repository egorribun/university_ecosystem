import type { ComponentPropsWithRef, ComponentPropsWithoutRef, ElementType } from "react"

export type PolymorphicRef<T extends ElementType> = ComponentPropsWithRef<T>["ref"]

export type PolymorphicComponentProps<
  T extends ElementType,
  Props extends Record<string, unknown> = Record<string, never>,
> = Props & { as?: T } & Omit<ComponentPropsWithoutRef<T>, keyof Props | "as">
