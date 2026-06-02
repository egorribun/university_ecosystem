# CI Linting & Test Suite Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal**: Establish actionlint workflow verification, expand Vitest forwarding modal test coverage, and clean up warnings/FFI import failures in the Python test suite.

**Architecture**: 
1. Hook `actionlint` into `.pre-commit-config.yaml` to validate GHA files locally and in CI checks.
2. Refactor `tests/contracts/test_ws_hub_contract.py` to catch `ImportError` on loading the native `pact` module, gracefully skipping execution on Windows machines.
3. Make `db.add` mock synchronous in `tests/test_events_unit.py` to resolve unawaited coroutine warnings.
4. Implement a comprehensive unit test suite in Vitest for the `ForwardModal` component in the frontend.

**Tech Stack**: Python (pytest), Go, React/TypeScript (Vitest, React Testing Library), GitHub Actions, pre-commit.

---

### Task 1: Add actionlint Pre-commit Hook

**Files:**
- Modify: `.pre-commit-config.yaml`

- [ ] **Step 1: Add actionlint repo config to pre-commit config**
  Edit `.pre-commit-config.yaml` and append the actionlint hook under `repos`.
  
  ```yaml
    - repo: https://github.com/rhysd/actionlint
      rev: v1.7.12
      hooks:
        - id: actionlint
  ```

- [ ] **Step 2: Run actionlint via pre-commit to check workflows**
  Run: `pre-commit run actionlint --all-files`
  Expected: All workflow files in `.github/workflows/` are linted successfully and pass.

- [ ] **Step 3: Commit changes**
  Run:
  ```bash
  git add .pre-commit-config.yaml
  git commit -m "ci: add actionlint pre-commit hook to lint github workflows"
  ```

---

### Task 2: Polish Python test warnings in test_events_unit.py

**Files:**
- Modify: `tests/test_events_unit.py`

- [ ] **Step 1: Make db.add mock synchronous in mock_db fixture**
  Update the `mock_db` fixture inside `tests/test_events_unit.py` to explicitly set `db.add = MagicMock()`.
  
  ```python
  @pytest.fixture
  def mock_db():
      db = AsyncMock()
      db.add = MagicMock()
      return db
  ```

- [ ] **Step 2: Run pytest to verify warning is resolved**
  Run: `uv run pytest tests/test_events_unit.py -v`
  Expected: All tests pass, and the unawaited coroutine `RuntimeWarning` from `db.add` is gone.

- [ ] **Step 3: Commit changes**
  Run:
  ```bash
  git add tests/test_events_unit.py
  git commit -m "test(backend): make db.add mock synchronous to fix RuntimeWarning"
  ```

---

### Task 3: Handle Pact Windows DLL import failures gracefully

**Files:**
- Modify: `tests/contracts/test_ws_hub_contract.py`

- [ ] **Step 1: Replace pytest.importorskip with try-except in test_ws_hub_contract.py**
  Replace lines 34-36 in `tests/contracts/test_ws_hub_contract.py` with a try-except block that skips the module if `pact` fails to load.
  
  ```python
  pact_lib = None
  try:
      import pact
      pact_lib = pact
  except ImportError:
      pass

  if pact_lib is None:
      pytestmark = pytest.mark.skip(reason="pact-python is not installed or failed to load DLL (e.g. on Windows)")
      class DummyPact:
          pass
      Pact = DummyPact
      match = None
  else:
      Pact = pact_lib.Pact
      match = pact_lib.match
  ```

- [ ] **Step 2: Run pytest on the contract test file**
  Run: `uv run pytest tests/contracts/test_ws_hub_contract.py -v`
  Expected: The tests are skipped gracefully with the skipping reason, rather than raising a Warning/Error at test collection.

- [ ] **Step 3: Commit changes**
  Run:
  ```bash
  git add tests/contracts/test_ws_hub_contract.py
  git commit -m "test(backend): skip pact contract tests gracefully on DLL import failure"
  ```

---

### Task 4: Add ForwardModal UI unit tests

**Files:**
- Create: `frontend/src/components/messenger/__tests__/ForwardModal.test.tsx`

- [ ] **Step 1: Write ForwardModal.test.tsx**
  Create the unit test file `frontend/src/components/messenger/__tests__/ForwardModal.test.tsx` to verify all cases of ForwardModal:
  
  ```typescript
  import { render, screen, fireEvent } from "@testing-library/react"
  import { describe, expect, it, vi } from "vitest"
  import { ForwardModal } from "@/components/messenger/ForwardModal"
  import type { Contact } from "@/components/messenger/types"

  vi.mock("react-i18next", () => ({
    useTranslation: () => ({
      t: (key: string) => key,
    }),
  }))

  vi.mock("@/components/media/SmartImage", () => ({
    default: ({ alt, className }: { alt?: string; className?: string }) => (
      <img alt={alt} className={className} />
    ),
  }))

  vi.mock("@/hooks/useFocusTrap", () => ({
    default: () => ({ current: null }),
  }))

  const mockContacts: Contact[] = [
    { id: "c1", name: "Alice", avatar: null, lastMessage: "Hey" },
    { id: "c2", name: "Bob", avatar: "http://bob.png", lastMessage: "Hello" },
  ]

  describe("ForwardModal", () => {
    it("renders nothing when open=false", () => {
      const { container } = render(
        <ForwardModal open={false} onClose={vi.fn()} contacts={mockContacts} onSelect={vi.fn()} />
      )
      expect(container.firstChild).toBeNull()
    })

    it("renders dialog with proper ARIA when open=true", () => {
      render(
        <ForwardModal open={true} onClose={vi.fn()} contacts={mockContacts} onSelect={vi.fn()} />
      )
      const dialog = screen.getByRole("dialog")
      expect(dialog).toBeTruthy()
      expect(dialog.getAttribute("aria-modal")).toBe("true")
      expect(dialog.getAttribute("aria-labelledby")).toBeTruthy()
      expect(screen.getByRole("listbox")).toBeTruthy()
    })

    it("renders list of contacts and matches currentChatId", () => {
      render(
        <ForwardModal
          open={true}
          onClose={vi.fn()}
          contacts={mockContacts}
          currentChatId="c1"
          onSelect={vi.fn()}
        />
      )
      expect(screen.getByText("Alice")).toBeTruthy()
      expect(screen.getByText("messenger:forwardCurrentChat")).toBeTruthy()
      expect(screen.getByText("Bob")).toBeTruthy()
    })

    it("renders empty state when contacts list is empty", () => {
      render(
        <ForwardModal open={true} onClose={vi.fn()} contacts={[]} onSelect={vi.fn()} />
      )
      expect(screen.getByText("messenger:forwardNoChats")).toBeTruthy()
      expect(screen.queryByRole("listbox")).toBeNull()
    })

    it("triggers onSelect callback when contact is selected", () => {
      const onSelect = vi.fn()
      render(
        <ForwardModal open={true} onClose={vi.fn()} contacts={mockContacts} onSelect={onSelect} />
      )
      fireEvent.click(screen.getByRole("option", { name: /Alice/ }))
      expect(onSelect).toHaveBeenCalledWith("c1")
    })

    it("triggers onClose callback when close button or backdrop is clicked", () => {
      const onClose = vi.fn()
      render(
        <ForwardModal open={true} onClose={onClose} contacts={mockContacts} onSelect={vi.fn()} />
      )
      fireEvent.click(screen.getByRole("button", { name: "common:buttons.close" }))
      expect(onClose).toHaveBeenCalledTimes(1)

      const backdrop = document.querySelector('[aria-hidden="true"]')
      expect(backdrop).toBeTruthy()
      fireEvent.click(backdrop!)
      expect(onClose).toHaveBeenCalledTimes(2)
    })
  })
  ```

- [ ] **Step 2: Run Vitest to check new tests pass**
  Run: `npx vitest run src/components/messenger/__tests__/ForwardModal.test.tsx --config frontend/vitest.config.ts`
  Expected: PASS.

- [ ] **Step 3: Run full Vitest suite to ensure coverage thresholds hold**
  Run: `npm run test:ci --prefix frontend`
  Expected: All tests pass, and coverage thresholds (>=70% functions, etc.) are successfully met.

- [ ] **Step 4: Commit changes**
  Run:
  ```bash
  git add frontend/src/components/messenger/__tests__/ForwardModal.test.tsx
  git commit -m "test(frontend): add ForwardModal component unit tests"
  ```
