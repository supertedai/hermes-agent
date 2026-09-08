# Verification gates

Observed results:

- Baseline regression test was red: with the implementation reverted, `markdown-text.fallback.test.tsx` could not find the rendered `Fallback heading`.
- Focused post-fix tests: 54 passed across preprocess, fallback, and overflow suites.
- Desktop UI typecheck: passed (`npx tsc -p tsconfig.json --noEmit`).
- ESLint on changed source/test: passed.
- `git diff --check`: passed.
- Diff scope: renderer source, one regression test, and this ADR package; unrelated main-checkout changes remain untouched.

Still required:

- Independent review and disposition.
- Runtime readback after human landing confirming assistant DOM contains rendered heading/list/strong/code elements and does not expose raw Markdown markers as the rendered surface.
