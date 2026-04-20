## Python

- Always use **uv**. Never pip, poetry, pipenv, or conda.
- Commands: `uv init`, `uv add`, `uv run`, `uv venv`, `uv pip install -r requirements.txt`
- Type hints on all functions. Prefer `pathlib` over `os.path`.
- Use `ruff` for formatting. Concise docstrings only where logic isn't obvious.

## Mermaid Diagrams

- Use liberally for architecture, data flows, sequences, timelines.
- Use `<br>` for line breaks inside node labels.
- **Never** use bullet characters (`•`, `-`, `*`) or numbered lists (`1.`, `2.`) inside node labels — Obsidian rejects these as "Unsupported markdown: list".
- Use comma-separated text instead: `"_id→id, TO_JSON_STRING,<br>soft-delete filter"`
- **Never put `[[wikilinks]]` inside Mermaid node labels.** Mermaid parses `[[...]]` as its *subroutine shape*, not as Obsidian wikilinks. At best it silently renders as an unexpected shape; at worst (e.g. `NODE[[name]] / [[other]]:::cls` chains) it breaks the whole diagram parse. Instead: put plain-text service names inside node labels, then list the `[[links]]` in a one-line wikilinks footer below the diagram (prose — preserves graph connectivity + gives readers click-through).
- **Never put `{curly}` braces, parens-in-parens, or complex markdown inside node labels** — the Mermaid parser gets confused. Keep labels plain.
- For sequence diagrams: `participant Alias as Display Name` — don't use `[[...]]` as the display name. Reference the service via the wikilinks footer instead.

## Obsidian Markdown

- **Wikilinks**: `[[page-name]]` or `[[page-name|Display Text]]` — never relative markdown links.
- **Callouts**: `> [!note]`, `> [!warning]`, `> [!tip]`
- **Tags**: YAML frontmatter `tags: [tag1, tag2]` — not inline `#tags`.
- **Aliases**: `aliases: [alt-name]` for pages with multiple names.
- **Code blocks**: Fenced with language identifiers.

## Wiki Page Frontmatter

Every wiki page must have:

```yaml
---
title: Page Title
type: entity | concept | source | project | todo
created: YYYY-MM-DD
updated: YYYY-MM-DD
confidence: 0.0-1.0
sources: []
tags: []
---
```

Confidence: 0.9+ verified, 0.7 supported, 0.5 single source, 0.3 inferred, 0.1 speculative.

## Wiki Naming

- Files: `kebab-case.md`
- Sources: `source-YYYY-MM-DD-short-title.md`
- Log entries: `## [YYYY-MM-DD] operation | Brief Title`

## Writing Style

- Tables over prose when presenting structured data.
- Be thorough in analysis, concise in output.
- Cite file paths when referencing code: `github/airflow/dags/some_dag.py`
- Always update `wiki/index.md` and `wiki/log.md` after creating/moving pages.
