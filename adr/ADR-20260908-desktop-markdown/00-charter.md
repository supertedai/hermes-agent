# ADR-20260908: Desktop assistant Markdown rendering

Owner: Morten (human landing gate); implementer: Opus
Status: proposed / pre-implementation

## Request
Fix the desktop regression shown in the supplied screenshot: assistant Markdown is displayed as raw `##`, `**`, and fenced-code markers in a monospace block instead of rendered Markdown.

## Scope
Inspect and minimally fix the assistant Markdown rendering path under `apps/desktop/src/components/assistant-ui/`. Preserve unrelated dirty changes in the main checkout. No runtime-only edits.

## Exit criterion
A focused regression test proves representative assistant Markdown reaches rendered DOM elements (heading, strong, list, code) rather than raw marker text; oversized/failure fallback behavior remains bounded and explicit. The change is reviewed, committed, and runtime verification is separately read back after human landing.
