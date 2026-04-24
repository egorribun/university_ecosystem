# ADR-017: Division of Tests into test_wave*.py Files

## Status
Accepted (with planned deprecation)

## Context
During a period of rapid development and strict coverage requirements, the Python backend test suite experienced a significant expansion. To quickly boost code coverage across various untested modules (e.g., specific edge cases in authentication, cache invalidation, and event handling) without disrupting existing, stable test files, a strategy of creating isolated "wave" files was adopted.

These files were named sequentially, such as `test_wave6_coverage.py`, `test_wave7_coverage.py`, up to `test_wave10_coverage.py`. Additionally, files like `test_coverage_boost_v2.py` were created.

## Decision
We accepted the temporary use of `test_wave*.py` files as a tactical mechanism to rapidly increase code coverage and stabilize the build pipeline during critical audit phases. 

However, we recognize this as technical debt. The long-term decision is to **consolidate and refactor** these wave files into their appropriate domain-specific test suites.

## Rationale
- **Speed of Execution**: Creating new, isolated test files prevented merge conflicts and reduced the cognitive load required to understand and integrate with existing, complex test setups.
- **Audit Traceability**: The "wave" terminology maps directly to specific internal audit phases and sprints where coverage gaps were systematically identified and closed.
- **Maintainability Drawback**: While effective tactically, grouping tests by the *time they were written* rather than the *domain they test* makes it extremely difficult for future developers to find existing tests for a specific feature, leading to duplicated test logic and fragmented maintenance.

## Consequences
- **Current State**: The repository contains several `test_wave*.py` files that successfully provide required coverage.
- **Action Item**: As part of ongoing repository polishing (Task 5b and 5c), these files will be systematically refactored. For example, tests for MFA inside a wave file will be moved to `test_mfa.py` or `test_auth.py`, and tests for event categories will move to `test_events.py`.
- **Future Policy**: New tests should be placed in domain-specific files (`test_<module>.py`). The "wave" or "boost" naming convention is deprecated for future additions.
