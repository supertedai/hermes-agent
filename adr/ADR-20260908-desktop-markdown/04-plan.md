# Plan

1. Reproduce the reported fallback with the smallest representative content and inspect exact runtime error.
2. Add a failing DOM regression test for rendered Markdown.
3. Implement one root-cause fix only.
4. Run focused UI tests, typecheck, and lint/gates.
5. Obtain independent review and disposition findings.
6. Commit exact diff, push branch, read back remote state.
7. After human landing, apply the exact commit and verify live desktop rendering.
