---
name: universal-code-reviewer
description: >
  A fully self-contained, context-aware code review skill that automatically detects the project domain
  and technology stack, spawns 3 dynamically tailored specialist sub-agents, runs a baseline bug sweep,
  performs a deep multi-perspective scan, synthesizes all findings into a structured Markdown report, and
  saves it to reports/bug_scans/ with a dated filename. Use this skill whenever the user asks to review,
  audit, scan, or find bugs in any code file, module, directory, or codebase — even if they don't say
  "code review" explicitly. Trigger for requests like "check this for bugs", "review my scraper", "audit
  this module", "what's wrong with this file", or "find issues in my code". Works for ALL project types:
  web scrapers, REST APIs, database schemas, IaC, UI components, ML pipelines, CLI tools, and more.
---

# Universal Code Reviewer

A fully adaptive code review skill. Every invocation follows the same six-phase pipeline — but the
specialist agents and their lenses are regenerated fresh based on the actual code being reviewed.

---

## Phase 1 — Context Analysis

Before doing anything else, read the target file(s) or module the user pointed at. Your goal is to
determine two things:

1. **Domain** — what is this code actually doing? (e.g., Web Scraper, REST API, Database ORM Layer,
   Infrastructure as Code, React UI Component, ML Training Pipeline, CLI Tool, Data ETL)
2. **Stack** — what languages, frameworks, and key libraries are in play?

Keep this phase brief — a short internal paragraph is enough. You'll use these two answers to configure
everything that comes next.

---

## Phase 2 — Dynamic Agent Spawning

Based on the domain you identified, define **exactly 3 specialist reviewer personas**. Each persona must:

- Have a name that reflects their specific lens (not generic titles like "Agent A")
- Have a focused mandate matched to the failure modes most likely in this domain
- Know which parts of the code to prioritize

### Domain → Agent Mapping (examples, not exhaustive)

Use these as starting patterns. Adapt freely — the goal is maximum coverage of the real risks for this
specific code.

| Domain | Suggested Agent Trio |
|---|---|
| Web Scraper | Stealth & Anti-Detection · Parsing & Extraction Robustness · Session & State Management |
| REST API / Backend | Security & Auth · Performance & N+1 Queries · Architecture & Contract Integrity |
| Database Schema / ORM | Data Integrity & Constraints · Query Safety & Injection · Migration & Drift Risk |
| Infrastructure as Code | Security Posture & Least Privilege · Idempotency & Drift · Cost & Resource Waste |
| React / UI Component | Accessibility & UX Edge Cases · State & Side-Effect Correctness · Performance & Re-render |
| ML / Training Pipeline | Data Leakage & Reproducibility · Numerical Stability · Resource & Memory Efficiency |
| CLI Tool | Input Validation & Injection · Error UX & Exit Codes · Cross-Platform Compatibility |
| ETL / Data Pipeline | Schema Drift & Type Coercion · Failure Recovery & Idempotency · Throughput & Backpressure |

Spawn the 3 agents now (sub-agents if the environment supports them; otherwise perform each review pass
yourself in sequence, clearly separating the perspectives). Tell each agent their name, mandate, and what
to look for.

---

## Phase 3 — Baseline Sweep (Always Runs First)

Regardless of domain, perform a universal baseline pass before the specialists begin. Flag any of the
following found anywhere in the target code:

- Syntax errors or invalid constructs
- Unhandled exceptions and bare `except`/`catch` blocks that swallow errors silently
- Missing imports or imports that are defined but never used
- Obvious type mismatches or unsafe casts
- Dead code and unreachable branches
- Hardcoded secrets, credentials, API keys, or tokens
- Missing null/None/undefined guards on values that are clearly nullable
- Basic logic flaws (off-by-one, inverted conditions, always-true/always-false predicates)

Output these findings as a structured list — one finding per line, with file path and line number where
possible.

---

## Phase 4 — Multi-Agent Deep Scan

Each of the 3 specialist agents now reviews the code through their dedicated lens. Each agent must:

- Identify concrete, specific bugs or risks — not vague suggestions
- Cite file names and line numbers whenever possible
- Rate each finding by severity: **Critical** / **High** / **Medium** / **Low**
- Briefly explain *why* the issue matters in context (a reader unfamiliar with this codebase should
  understand the consequence)

Agents should not repeat findings already caught in the Baseline Sweep. They go deeper into domain-
specific failure modes.

---

## Phase 5 — Synthesis & Report Formatting

Compile all findings from Phases 3 and 4 into a single Markdown report using this exact structure:

```
# Code Review Report — [Module/File Name]

**Date:** YYYY-MM-DD  
**Domain:** [identified domain]  
**Stack:** [identified stack]  
**Reviewed by:** Universal Code Reviewer + [Agent 1 Name], [Agent 2 Name], [Agent 3 Name]

---

## Baseline Sweep

[findings from Phase 3, or "No baseline issues found."]

---

## [Agent 1 Name] Review

[findings from this agent, with severity labels]

---

## [Agent 2 Name] Review

[findings from this agent, with severity labels]

---

## [Agent 3 Name] Review

[findings from this agent, with severity labels]

---

## Remediation Steps

[Prioritized, actionable list of fixes — Critical and High items first. Each step should be concrete
enough that a developer can act on it without needing to re-read the full report.]
```

Do not trim or summarize findings — include everything. The report should stand alone.

---

## Phase 6 — Automatic File Save

Save the completed report to disk immediately after synthesis.

**Target directory:** `reports/bug_scans/` relative to the project root.  
Create the directory (including any missing parent directories) if it does not exist.

**Filename convention:** `YYYY-MM-DD-[brief-description-of-module-reviewed].md`

- Use today's date for `YYYY-MM-DD`
- For the description, derive a short kebab-case slug from the module or file name being reviewed
  (e.g., `scraper-core`, `auth-middleware`, `user-schema`, `main-pipeline`)
- Example: `2026-04-21-scraper-core.md`

After saving, tell the user the full path to the saved report.

---

## Invocation

When the user says something like "review my scraper", "audit this module", "find bugs in X", or points
you at a file or directory without further instruction — start Phase 1 immediately. No need to ask for
clarification unless the target is genuinely ambiguous (e.g., the user said "review it" with no prior
context and there are many files in the project).

If the user specifies a focus area (e.g., "focus on security"), use it to bias which of the 3 specialist
agents you pick — but still run all 6 phases.

---

## Environment Notes

- **Sub-agents available (Claude Code):** Spawn Phases 1–4 in parallel where possible — Phase 1 first
  to get the domain, then Phases 3 and 4 (baseline + all 3 specialists) in the same turn.
- **No sub-agents (Claude.ai):** Run each phase sequentially in a single response. Clearly delimit each
  agent's section with a header so the output remains readable.
- **File saving:** Use the Write or Bash tool to create the directory and save the report. Prefer
  creating the directory with `mkdir -p` before writing the file.
