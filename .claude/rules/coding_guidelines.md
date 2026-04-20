# Coding Guidelines

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

- these guidelines are specifically for coding tasks. For non-coding tasks, use judgment to apply the relevant principles.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State assumptions up front as "Assuming X, Y, Z — correct me or I proceed." Do this before touching any file on a non-trivial task.
- Ambiguity test: if resolving it would change *which file* you touch or *which function* you call, stop and ask. If it only changes a name or a trivial default, pick, note the choice in the response, and proceed.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- Before finishing, re-read the diff and delete anything speculative. Speculation is:
  - config flags, parameters, or env vars nobody asked for
  - try/except around conditions that cannot occur in the current call sites
  - base classes, protocols, or interfaces with a single concrete implementation
  - helper functions called from exactly one site
  - tests for behavior that isn't in the spec
- If the diff exceeds ~150 lines for a task that sounded small, stop and justify each file touched in one sentence. Most of the time the extra lines reveal over-reach.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

Scope-inflation guard: if you find yourself about to open a file that isn't directly named or implied by the task, stop, name why it's needed, and wait for confirmation before editing it.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"
- "Change a config value" → "Show the rendered config and the before/after diff"
- "Update a wiki page" → "Confirm wikilinks resolve and `log.md` has the entry"
- "Add a dbt model" → "`dbt compile` succeeds and the SQL output matches the expected shape"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

Stop condition: if the same verification fails twice in a row, stop and report what was tried — do not keep retrying. Two failures mean the theory is wrong, not the attempt.

## 5. Evidence on Completion

Don't claim done without proof. When reporting a task complete, name the evidence:

- the test name that now passes (e.g. `test_invalid_input_rejects`)
- the command output line that confirms it (e.g. `dbt run ... PASS=3 WARN=0 ERROR=0`)
- the `file:line` where the behavior now lives
- the exact manual step you ran and the observed result

"It should work," "this looks right," and "I believe this fixes it" are not evidence. If the task is hard to verify, say so explicitly instead of implying success.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
