# Decision

Use the smallest root-cause fix in the existing assistant Markdown pipeline. Keep `HugeTextFallback` for true oversized content and genuine render failures. Add a behavior-level test at the component seam, not a source-shape test.

Classification: Material UI behavior change. Blast radius is all assistant, reasoning, tool, user-bubble, and imported-history content using `MarkdownTextContent`; reversibility is high via Git revert; no privilege/schema/runtime boundary is changed.

No runtime application is part of implementation. Human owns landing/merge.
