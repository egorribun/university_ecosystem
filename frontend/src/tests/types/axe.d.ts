import type { AxeMatchers } from "jest-axe"

/* eslint-disable @typescript-eslint/no-empty-object-type */
declare module "vitest" {
  export interface Assertion extends AxeMatchers {}
  export interface AsymmetricMatchersContaining extends AxeMatchers {}
}
