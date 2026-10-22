import "vitest"

declare module "vitest" {
  export interface Assertion<R extends void | Promise<void> = void, T = unknown> {
    toHaveNoViolations(this: Assertion<R, T>): R
  }
}
