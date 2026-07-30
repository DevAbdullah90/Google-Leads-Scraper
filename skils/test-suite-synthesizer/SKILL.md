---
name: test-suite-synthesizer
description: >
  Generates a complete, production-grade test suite for any module or file the user points at.
  Operates at senior-staff engineering level: analyzes the project stack, retrieves historical
  regressions from bug scan changelogs, then writes tripartite coverage (happy path, edge/chaos,
  regression locks) with strict mocking of all external I/O. Saves files in the correct framework
  convention automatically. Use this skill whenever the user asks to "write tests", "generate a
  test suite", "add test coverage", "create unit tests", "add regression tests", or points at a
  file/module and says anything like "test this" or "cover this". Trigger even when the user only
  says "tests for X" — any request that implies generating automated tests for code should invoke
  this skill.
---

# Test-Suite Synthesizer

A strict, six-phase pipeline. Every invocation follows the same sequence.
The goal is not maximum coverage percentage — it is maximum regression prevention with minimum brittleness.

---

## Phase 1 — Stack Fingerprinting

Before writing a single test, fully understand the project. Read the following files (whichever exist):

- `requirements.txt`, `pyproject.toml`, `setup.cfg` → Python stack, test libraries
- `package.json`, `tsconfig.json` → JS/TS stack, test runner, module system
- `jest.config.*`, `vitest.config.*`, `pytest.ini`, `conftest.py` → existing test configuration
- `Dockerfile`, `docker-compose.yml` → external service dependencies (DBs, queues, caches)
- Any existing test files to understand established mocking patterns and fixture conventions

From this, determine and record:

1. **Language**: Python / TypeScript / JavaScript / other
2. **Test framework**: Pytest / Jest / Vitest / Mocha / other
3. **Async model**: asyncio + pytest-asyncio / Promise-based / synchronous
4. **External dependencies to mock**: HTTP clients (httpx, axios, requests), databases (PostgreSQL, Redis, pgvector, SQLAlchemy ORM), browser automation (Playwright, Puppeteer), file I/O (aiofiles, fs), third-party SDKs
5. **Pydantic version** (if Python): v1 vs v2 changes model construction in tests
6. **Module system** (if JS/TS): ESM vs CommonJS affects how jest.mock / vi.mock works
7. **Output file path and name** (determined by convention — see Phase 6)

If the stack is ambiguous, prefer the most common convention for the detected language before asking.

---

## Phase 2 — Historical Regression Retrieval

Scan `reports/bug_scans/` for every file ending in `_CHANGELOG.md`.

For each changelog found that is relevant to the target module (match by file path, function name, or module name mentioned in the changelog):

- Extract every **Fix Applied** entry
- Note the exact file, line range, and the described failure mode
- Note any bugs listed under **Deferred / Skipped** that are still open risks

Compile a **regression manifest**: a list of `(bug_id, failure_mode, affected_function)` tuples. This manifest drives Phase 5.

If no changelogs exist or none are relevant, note that and proceed — regression locks will be written based on code analysis alone.

---

## Phase 3 — Target Module Analysis

Read the target module(s) in full. For each function or method, identify:

- **Inputs**: types, optional/required, edge values (None, empty string, zero, negative, very large)
- **Outputs**: return type, possible None / error paths
- **Side effects**: file writes, network calls, database mutations, state changes
- **Async boundaries**: which calls are awaited, which are synchronous
- **Error handling**: what exceptions are caught, which are re-raised, which are swallowed
- **Business logic invariants**: the core rules the function must always uphold

Write down a plain-English description of what the function is SUPPOSED to do before writing any test. This is your ground truth. A test that doesn't check an invariant is deadweight.

---

## Phase 4 — Mocking Strategy

For every external dependency identified in Phase 1 and confirmed present in the target module, define a mock. The rule: **no test may touch real I/O** — no real network requests, no real database connections, no real file system writes (unless the test is explicitly an integration test and the user requested one).

### Python mocking patterns

```python
# Async functions
from unittest.mock import AsyncMock, MagicMock, patch

# httpx
with patch("module.httpx.AsyncClient") as mock_client:
    mock_client.return_value.__aenter__.return_value.get = AsyncMock(
        return_value=MagicMock(status_code=200, content=b"...", text="...")
    )

# aiofiles
with patch("module.aiofiles.open", new_callable=MagicMock) as mock_open:
    mock_open.return_value.__aenter__.return_value.write = AsyncMock()
    mock_open.return_value.__aenter__.return_value.read = AsyncMock(return_value="data")

# Playwright page
mock_page = AsyncMock()
mock_page.goto = AsyncMock()
mock_page.query_selector = AsyncMock(return_value=None)
mock_page.query_selector_all = AsyncMock(return_value=[])

# PostgreSQL / SQLAlchemy
with patch("module.db_session") as mock_session:
    mock_session.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[])))
```

### JavaScript / TypeScript mocking patterns

```typescript
// jest / vitest — module mock
jest.mock("../lib/db", () => ({ query: jest.fn().mockResolvedValue({ rows: [] }) }));

// fetch / axios
global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => ({}) });

// fs/promises
jest.mock("fs/promises", () => ({ writeFile: jest.fn(), readFile: jest.fn() }));
```

For mocks that need to simulate failures (network timeout, disk full, DB connection error), prepare separate mock variants — you will need them in Phase 5.

---

## Phase 5 — Tripartite Test Generation

Generate tests in three clearly labelled sections. Every test must have a descriptive name that reads as a sentence explaining what it verifies. Never name a test `test_1` or `it("does stuff")`.

### Section A — Standard Use Cases (Happy Path)

Cover the core business logic under normal, expected inputs. Each test should:
- Set up realistic (not toy) input data
- Call the function under test with mocks in place
- Assert on the actual return value AND on mock call signatures where they matter
- Be deterministic: the same inputs always produce the same outputs

Aim for one test per meaningful code path through the function, not one test per line.

### Section B — Edge Cases & Chaos

Cover the inputs and conditions that expose fragility. Think like an attacker or an ops engineer at 3am:

- **Null / None / undefined inputs** on every parameter that doesn't have a not-null guarantee
- **Empty collections**: empty list, empty string, empty dict, zero-length file
- **Type mismatches**: wrong type passed where the function doesn't validate
- **Numeric extremes**: zero, negative, `float("inf")`, very large integers, floating-point precision
- **Async race conditions**: simulate concurrent calls to shared state; use `asyncio.gather` for Python async functions
- **Rate limit / timeout simulation**: mock the HTTP client to raise `httpx.TimeoutException` or `asyncio.TimeoutError`
- **Partial failures**: mock a function that's called in a loop to succeed on the first 3 calls and fail on the 4th
- **Encoding issues**: non-ASCII characters, emoji, null bytes in strings
- **Large payloads**: inputs that would exceed a size cap you identified in the code

For each edge case, assert that the function either handles it gracefully (returns a sensible default) or raises the expected exception — not that it crashes silently.

### Section C — Regression Locks

One dedicated test per entry in the regression manifest from Phase 2. Each test must:

- Include a comment referencing the bug ID (e.g., `# Regression lock: SM-1`)
- Reproduce the exact conditions that triggered the original bug
- Assert the fixed behavior explicitly, not just "it doesn't crash"

If the regression manifest is empty, write regression locks based on the error-handling paths identified in Phase 3 — every swallowed exception and every silent fallback deserves a lock that verifies it produces the right outcome.

**Examples of regression lock patterns:**

```python
# Regression lock: SM-1 — append_business silently swallowed write failures
async def test_append_business_returns_false_on_write_failure():
    with patch("scraper.recovery.aiofiles.open", side_effect=OSError("disk full")):
        result = await append_business(Path("/tmp/out.json"), {"business_name": "Acme"})
    assert result is False  # must not raise, must signal failure to caller

# Regression lock: SM-2 — finalize_output deleted JSONL on corrupt JSON write
async def test_finalize_output_keeps_jsonl_if_json_is_corrupt(tmp_path):
    out = tmp_path / "results.json"
    out.write_bytes(b'{"broken": ')  # truncated / corrupt
    jsonl = out.with_suffix(".jsonl")
    jsonl.write_text('{"business_name": "Acme"}\n')
    # patching json.loads to simulate corruption detection
    with patch("scraper.recovery.json.loads", side_effect=json.JSONDecodeError("", "", 0)):
        await finalize_output(out, {}, delete_jsonl=True)
    assert jsonl.exists(), "JSONL backup must be preserved when output JSON is invalid"
```

---

## Phase 6 — File Output

Determine the output path from the project conventions established in Phase 1.

### Python (Pytest)

- Output directory: `tests/`
- File name: `test_<module_name>.py` (e.g., `tests/test_recovery.py`)
- Required header:
  ```python
  import pytest
  import asyncio
  import json
  from pathlib import Path
  from unittest.mock import AsyncMock, MagicMock, patch
  # ... project-specific imports
  ```
- Required fixture block (if async tests are present):
  ```python
  # pytest-asyncio configuration — add to conftest.py if not already present:
  # asyncio_mode = "auto"
  ```
- If `conftest.py` does not exist in `tests/`, create a minimal one with shared fixtures (tmp directories, mock factories for the most-used dependencies).

### JavaScript / TypeScript (Jest or Vitest)

- Output directory: `__tests__/` (or `src/__tests__/` — match the project's existing convention)
- File name: `<module_name>.test.ts` or `<module_name>.test.tsx`
- Required imports at top match the detected module system
- Wrap related tests in `describe` blocks by section (Happy Path / Edge Cases / Regression Locks)
- Include `beforeEach` / `afterEach` for mock reset: `jest.clearAllMocks()` or `vi.clearAllMocks()`

### Other languages

Apply the standard convention for the detected framework. When in doubt, use a `tests/` subdirectory and a file prefixed with `test_` or suffixed with `.test`.

After writing the file, **read it back** and verify:
- Every import resolves to a module that exists in the project
- Every mock patches the correct import path (the path as seen by the module under test, not the definition path)
- No test has a hard-coded absolute path or environment-specific value
- Async tests use the correct decorator or config for the detected framework

---

## Output Report

After saving the file, print a brief summary:

```
Test Suite Generated
────────────────────
File:       tests/test_recovery.py
Framework:  Pytest + pytest-asyncio
Tests:      24 total
  Section A (Happy Path):      8
  Section B (Edge/Chaos):      9
  Section C (Regression Locks): 7
Regressions covered: SM-1, SM-2, BS-2, PE-1, PE-3 (from 2026-04-21-scraper-module_CHANGELOG.md)
Mocks:      aiofiles.open, json.loads, pathlib.Path.read_text, pathlib.Path.unlink

Run with:   pytest tests/test_recovery.py -v
```

If `conftest.py` was created or modified, mention it.

---

## Quality Rules

These are non-negotiable constraints applied before saving:

1. **No real I/O.** Every network call, file write, and database query must be mocked.
2. **No magic numbers without a comment.** `timeout=30` needs `# matches PAGE_LOAD_TIMEOUT in settings`.
3. **No assert-True-on-everything.** Every assertion must check a specific value or behavior.
4. **No testing the mock itself.** If the only assertion is that a mock was called, add a second assertion that checks the return value or side effect too.
5. **Deterministic ordering.** Tests must not depend on execution order. Each test sets up and tears down its own state.
6. **The 99% realism standard.** Prefer tests that catch real bugs over tests that inflate coverage. One test that catches a silent data-loss bug is worth more than ten tests that verify a `__repr__` method.
