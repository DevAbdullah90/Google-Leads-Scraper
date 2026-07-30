---
name: autonomous-bug-solver
description: >
  A fully deterministic execution-partner skill that reads bug reports (either from the terminal
  prompt or automatically from the most recent Markdown file in reports/bug_scans/), plans every
  fix before touching a single line, applies precise and robust code changes, self-reviews for
  regressions, and saves a dated CHANGELOG file to reports/bug_scans/. Use this skill whenever
  the user asks to "fix the bugs", "solve the issues", "apply the fixes from the report", "patch
  this", "resolve these bugs", or pastes a list of bugs/issues and says to fix them. Trigger even
  if the user doesn't say "bug solver" — any request to programmatically resolve code issues,
  apply a review's findings, or execute a list of fixes should invoke this skill.
---

# Autonomous Bug Solver

A strict, five-phase execution pipeline. Every invocation follows the same sequence — no steps
are skipped, no fixes are applied before the plan is confirmed.

---

## Phase 1 — Input Parsing

Determine where the bugs are coming from.

### Case A: Bugs provided in the prompt
The user has pasted bug descriptions, error messages, or a list of issues directly in their
message. Use that as the bug list. Set `source_mode = "terminal"`.

### Case B: Read from the latest report file
The user said something like "fix the bugs", "apply the fixes", or "solve the issues" without
pasting specific bugs. In this case:

1. List all `.md` files in `reports/bug_scans/` (relative to the project root).
2. Select the **most recently modified** one that does NOT already end in `_CHANGELOG.md` —
   you want the source report, not a previous resolution log.
3. Read its full contents. This is your bug list.
4. Record its filename (e.g., `2026-04-21-scraper-module.md`) — you will need it in Phase 5.
5. Set `source_mode = "file"`.

If `reports/bug_scans/` does not exist or contains no eligible files, and no bugs were provided
inline, tell the user clearly and stop.

---

## Phase 2 — Execution Planning

Before modifying any file, output a clear execution plan. This is non-negotiable — it lets the
user catch mistakes before any code is changed.

The plan must list, for each bug you intend to fix:

```
### Fix N: [short title matching the bug ID or description]
- **File(s):** path/to/file.py (line N)
- **What changes:** one sentence describing the logic alteration
- **Why:** one sentence on the consequence being fixed
```

After presenting the plan, explicitly state which bugs you are **deferring or skipping** and why
(e.g., "SA-6 requires architectural changes beyond a local patch — skipping"). Be honest about
scope.

**Wait for the user to confirm before proceeding.** A simple "go ahead", "looks good", or "fix
them all" is sufficient. If the user asks to skip or modify specific items, update the plan
accordingly.

Do not apply any changes until the user gives the go-ahead.

---

## Phase 3 — Precision Execution

Apply the fixes in the order stated in the plan. Follow these principles:

### Accuracy over cleverness
Write straightforward, readable fixes. A correct three-line change is better than a clever
one-liner that might break under edge cases. Aim for 99% accuracy — prefer the obvious approach
over the elegant one when there is any doubt.

### Stack awareness
Before every change, consider:
- Does this affect a Pydantic model? Verify field names and types against the model definition.
- Does this affect an async function? Ensure awaits are correct and the event loop isn't blocked.
- Does this touch an import? Verify the import is at the module level and not duplicating an
  existing import.
- Does this affect a shared utility (e.g., `recovery.py`, `utils.py`)? Check every caller to
  ensure the signature change doesn't break other call sites.

### One fix at a time
Make each fix, read back the relevant lines, and confirm the change looks right before moving on
to the next. Do not batch all changes into a single write pass.

### Preserve style
Match the existing code style (indentation, quotes, naming conventions, comment style). Do not
reformat surrounding code.

---

## Phase 4 — Regression Check

After all fixes are applied, perform a strict self-review pass. For every file you modified:

1. **Read the file back** (or the relevant section) and check the modified lines.
2. Verify:
   - No new syntax errors (mismatched brackets, wrong indentation, unterminated strings).
   - No broken imports (every name imported is used; no import references a non-existent module
     or name).
   - No type mismatches introduced (e.g., a function that now returns `None` where a caller
     expects a `str`).
   - No broken call sites (if a function signature changed, every caller was updated).
   - No async/await violations (no `await` on a non-coroutine, no missing `await` on an async
     call).

Report the regression check results inline:
```
Regression check — file.py:
  ✓ Imports clean
  ✓ No syntax issues detected
  ✓ Return type consistent with callers
  ✗ [describe any issue found and fix it immediately]
```

If a regression is found during this phase, fix it immediately, then re-run the check on that
file before moving on.

---

## Phase 5 — Resolution Logging

Generate a Markdown changelog and save it to `reports/bug_scans/`.

### Filename rules

**If `source_mode = "file"`:**
Strip the `.md` extension from the source filename and append `_CHANGELOG.md`.
Example: `2026-04-21-scraper-module.md` → `2026-04-21-scraper-module_CHANGELOG.md`

**If `source_mode = "terminal"`:**
Generate a new filename: `YYYY-MM-DD-[brief-topic]_CHANGELOG.md`
Derive the topic slug from the dominant theme of the bugs fixed (2–4 kebab-case words).
Example: `2026-04-21-proxy-stealth-fixes_CHANGELOG.md`

### Changelog structure

```markdown
# Bug Fix Changelog

**Date:** YYYY-MM-DD
**Source:** [filename if file mode, or "terminal prompt" if terminal mode]
**Resolver:** Autonomous Bug Solver

---

## Summary
[2–3 sentence overview of what was fixed and why it mattered]

---

## Fixes Applied

### [Bug ID or short title]
- **File:** path/to/file.py
- **Line(s):** N–M
- **Change:** what was changed
- **Reason:** what was wrong and what the fix prevents

[repeat for each fix]

---

## Deferred / Skipped

### [Bug ID or short title]
- **Reason:** why it was skipped (architectural scope, requires human decision, out of bounds, etc.)

[repeat for each skipped item, or "None — all planned fixes applied." if everything was done]

---

## Files Modified
- path/to/file1.py
- path/to/file2.py

## Regression Check Results
- path/to/file1.py: ✓ clean
- path/to/file2.py: ✓ clean
```

After saving, tell the user the full path to the changelog file.

---

## Handling ambiguity

**Multiple eligible report files:** If there are multiple non-changelog `.md` files in
`reports/bug_scans/`, sort by modification time and pick the most recent. If two files have the
same modification timestamp, tell the user and ask which to use.

**Partial bug lists:** If the user provides some bugs inline but also references "the report",
merge both sources. Deduplicate by bug ID if they overlap.

**Bugs with no clear fix:** Some bugs in a report describe architectural concerns or require
product decisions (e.g., "rethink the proxy rotation strategy"). Do not attempt to fully
re-architect a system. Implement the minimal concrete fix described, note the broader concern in
the changelog's Deferred section, and flag it to the user.

**Missing files referenced in the plan:** If a file listed in the plan doesn't exist when you go
to edit it, stop and tell the user before making any other changes.

---

## What good execution looks like

- The plan is shown and confirmed before any code is touched.
- Each fix is applied cleanly to the smallest possible scope.
- Every modified file is read back to confirm the change.
- The regression check catches anything the fix might have broken.
- The changelog is specific: line numbers, exact behavior change, reason.
- Skipped items are documented honestly — the user knows what wasn't fixed and why.

The goal is not to fix everything at maximum speed. The goal is to fix the right things
correctly, leave the codebase in a better state than before, and give the user a clear record
of exactly what changed.
