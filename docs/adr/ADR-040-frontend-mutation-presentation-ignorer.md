# ADR-040: Frontend Mutation Presentation Ignorer

## Status

Accepted

## Date

2026-09-24

## Context

The frontend release gate requires a 100% viable Stryker score (AGENTS.md).
Producer shards run with `break: null` and always upload their report; the
aggregate `validate-stryker-inventory.mjs` is the only release decision and
stops at the first unacceptable mutant.

Every aggregate run since the policy was expanded failed on the same first
mutant (`shard-001:2 Timeout`, runs 35635039077 and 35730420629), so the rest
of the inventory was never reported. Reading the clear-text tables of the 32
completed shards of run 35954304649 showed 722 survivors, 5 timeouts, 2
NoCoverage and 5 errors across 60 files in half of the universe; about 1,500
survivors are expected overall.

A large share of them are `StringLiteral` mutants that replace a Tailwind
class list or a literal inline style value with `""`
(for example `Badge.tsx`: 82 survivors). Killing them means asserting CSS
class strings, which pins styling rather than behaviour and makes every visual
refactor a test change. Visual regression, axe and geometry specs already own
presentation.

On 2026-09-24 the maintainer chose a hybrid closure: kill every behavioural
survivor with tests, and exclude presentation-only literals through one
narrow, governed Stryker ignorer.

## Decision

`frontend/scripts/stryker-presentation-ignorer.mjs` defines the only allowed
ignore plugin, `presentation-class-names`. It ignores a mutant only when the
mutated node is a **string leaf** (a `StringLiteral`, or a `TemplateLiteral`
without interpolations) whose value position leads, through conditional
branches, logical operands, array elements, template parts and object
property values, to one of:

- a JSX attribute named `className` or `*ClassName`;
- an argument of `cn`, `clsx`, `cva`, `twMerge` or `twJoin`;
- the initializer of a binding named `*Classes`, `*ClassName` or
  `*ClassNames`;
- a property value inside the object literal of a JSX `style` attribute.

Everything else stays mutated. In particular: conditions and logical
operators that choose a class, object and array shapes, template literals
with interpolations, any `style` value that is not a literal (for example the
`minHeight` floor from `useStableListHeight`), and all non-class strings such
as labels, ARIA values, URLs and keys.

The policy is fail-closed at every evidence stage:

- `stryker.config.mjs` loads exactly this plugin and `ignorers:
  ["presentation-class-names"]`; `frontend-quality-contract.test.mjs` and
  `tests/test_quality_configuration.py` pin both.
- The instrumenter preflight and every report-config parity check compare
  against `canonicalInstrumenterConfig`; any other ignorer list, and any
  `Ignored` mutant whose reason is not the ADR-040 reason (for example a
  `// Stryker disable` directive), is rejected.
- The aggregate compares the set of `Ignored` mutants in each report with the
  independently regenerated preflight, so a report cannot mark an active
  mutant as ignored.
- Ignored mutants are counted in the inventory summary as `ignoredMutants`
  and excluded from the viable denominator; at least one killed mutant is
  still required.

## Consequences

- "100% viable" now means: every mutant that is not a governed presentation
  leaf or an explained compile error is killed.
- A styling decision (active tab, reduced motion, error state) still needs a
  killing test, because its condition is mutated.
- Class maps that are neither passed to a class helper nor bound to a
  `*Classes`/`*ClassName` name stay mutated; name them accordingly or test
  them.
- Widening the rule requires a new ADR and an update of
  `stryker-presentation-ignorer.test.mjs`, which pins exactly which sample
  mutants are ignored and which stay active.
