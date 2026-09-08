# Context and evidence

Observed evidence: screenshot `/home/morten/.hermes/images/upload_20260908_070543_1.png` shows the assistant answer inside the monospace bordered shape matching `HugeTextFallback` in `markdown-text.tsx`. Raw Markdown markers are visible.

Git baseline was inspected before editing. Main checkout is dirty in six unrelated Python files; those changes are preserved and excluded from this worktree. Baseline HEAD: `fef0e16fe1`.

Relevant path: `MarkdownTextSurface` uses `HugeTextFallback` when text exceeds `MAX_MARKDOWN_CHARS` or when the `ErrorBoundary` around `StreamdownTextPrimitive` catches a render error. Existing preprocessing tests pass, but they do not exercise the assistant component DOM path.

Unknown before repro: exact render error and whether the screenshot came from the character threshold or the ErrorBoundary fallback.
