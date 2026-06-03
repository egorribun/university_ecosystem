# Design Doc: CI Linting & Test Suite Polish

- **Date**: 2026-06-02
- **Status**: Proposed
- **Author**: Antigravity AI
- **Topic**: CI workflows linting, frontend forwarding tests, and backend test warnings/errors polish.

---

## 1. Goal & Context

The goal is to improve the quality of the CI pipeline, add missing test coverage for the recently introduced message forwarding UI component, and polish python test run execution by removing collection errors on Windows and warnings.

Current gaps and issues:
- **GitHub Actions workflows** are not linted. Syntax mistakes, unpinned actions, or incorrect contexts can lead to broken pipelines.
- **Message Forwarding UI Component (`ForwardModal.tsx`)** has 0% unit/integration test coverage in Vitest.
- **Pact contract tests (`test_ws_hub_contract.py`)** raise a blocking `ImportError` on Windows (DLL load failure on FFI module import), causing pytest collection warnings/errors.
- **Events Unit Tests (`test_events_unit.py`)** trigger a `RuntimeWarning: coroutine was never awaited` on `db.add` during event file upload mock testing.

---

## 2. Proposed Changes

### 2.1. CI Workflow Linting via actionlint Pre-commit Hook

We will add `actionlint` to [pre-commit config](file:///c:/Users/egorribun/Documents/university_ecosystem/.pre-commit-config.yaml) to parse and lint all GitHub Actions workflows in `.github/workflows/`. This guarantees that workflow files are checked on every commit locally and in CI.

**Configuration Update**:
```yaml
  - repo: https://github.com/rhysd/actionlint
    rev: v1.7.12
    hooks:
      - id: actionlint
```

### 2.2. Frontend ForwardModal Vitest Coverage

We will create a new test suite [ForwardModal.test.tsx](file:///c:/Users/egorribun/Documents/university_ecosystem/frontend/src/components/messenger/__tests__/ForwardModal.test.tsx) to verify the behavior and accessibility of the forwarding dialog.

**Test cases to implement**:
- It should render nothing when `open=false`.
- It should render a dialog with proper ARIA attributes (`role="dialog"`, `aria-modal="true"`, `aria-labelledby`, `role="listbox"`, `role="option"`) when `open=true`.
- It should show the list of contacts as destinations and display their names/avatars.
- It should display a `(current)` badge if the contact ID matches the `currentChatId`.
- It should render an empty state text and icon if the contacts array is empty.
- It should call `onSelect` with the selected contact ID when a row button is clicked.
- It should call `onClose` when the close button, backdrop, or Escape key is pressed.

### 2.3. Python Backend Pact Skipping & Warnings Cleanup

- **Skip Pact on Windows/DLL Failure**: In [test_ws_hub_contract.py](file:///c:/Users/egorribun/Documents/university_ecosystem/tests/contracts/test_ws_hub_contract.py), wrap the `pact` import in a try-except block. If `ImportError` is raised, gracefully define dummy classes/constants and skip the module using `pytestmark = pytest.mark.skip(...)`. This resolves the Windows import blocker without breaking Linux CI contract runs.
- **Fix Unawaited mock_db.add Coroutine**: In [test_events_unit.py](file:///c:/Users/egorribun/Documents/university_ecosystem/tests/test_events_unit.py), modify the `mock_db` fixture so that `db.add` is explicitly mocked as a synchronous `MagicMock`, preventing it from returning an unawaited coroutine.

---

## 3. Verification Plan

### 3.1. Automated Verification
- **Pre-commit actionlint**: Run `pre-commit run actionlint --all-files` to check all `.github/workflows/` files.
- **Frontend Vitest**: Run `npm run test:ci --prefix frontend` (or specific run for `ForwardModal.test.tsx`) to verify all tests pass.
- **Backend Pytest**: Run `uv run pytest --ignore=tests/contracts/test_ws_hub_contract.py -q` and verify the `RuntimeWarning` is gone. Run `uv run pytest tests/contracts/test_ws_hub_contract.py` on Windows to verify the Pact test skips gracefully.
