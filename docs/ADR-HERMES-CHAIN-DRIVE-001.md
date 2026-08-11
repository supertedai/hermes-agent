# ADR-HERMES-CHAIN-DRIVE-001 — Preflight measures the leased scope, and the driver never judges

**Status:** `ACCEPTED_ARCHITECTURE / RUNTIME_GATED`
**Parent:** `CAD-HERMES-CHAIN-DRIVE-001`
**Phase:** `P8` entry work; P8 stays `BLOCKED_BY_P1_P2_P4_P5`

## Decision 1 — step 4 measures the LEASED SCOPE, not the whole repository

`PreflightGate`'s own contract, stated in its docstring, lists three checks. Point 2
reads verbatim:

> 2. those leased files are clean

The implementation measured `git status --porcelain` over the entire repository.
Measured 2026-08-11: ~120–130 dirty files from parallel streams (129 at the last
reading — the number MOVES, which is the point), and all seven goals
blocked on `git target is dirty or has unowned changes`, uninterrupted.

In a worktree shared by eight streams, repository-wide cleanliness is unattainable
by construction. The gate could not be opened by any legitimate sequence of
actions, which is the same falsifier `BL-4029 L4` applied when it split one
impossible gate into three possible ones. `scope_is_clean` makes the implementation
match the contract that was already written.

The scope set is one set, used three times, and that is what makes this a contract
fix rather than a loosening:

```text
lease_authority.scope_paths(repo_scope)
    -> scope_is_clean   checks THESE files are clean          (step 4)
    -> lease_take       claims THESE files at the authority   (step 6)
    -> build_callable   binds the writer to source_refs[lease] (step 8)
```

The gate checks exactly the files the writer is permitted to touch.

**What actually discharges the obvious counterexample.** Goal A builds `agent/a.py`
while another stream holds uncommitted `agent/b.py` that `a.py` imports; tests would
then pass against foreign uncommitted code — the `BL-3643` defect, where the live
chat path depended on a symbol that existed only in the worktree.

That is NOT discharged by recording the surrounding dirt. `repo_dirty_files` and
`scope_dirty` are readback aids; as a guard they would be a fig leaf. It is
discharged **structurally**: the build root is `git archive <verified sha>`, so
foreign uncommitted files are physically absent from the tree the build and its
tests run in. That property is now MEASURED —
`test_isolated_build_root_actually_archives_the_given_sha` builds a two-commit
repo with a foreign uncommitted file and asserts both halves. Until round 3 it was
asserted only: the function was monkeypatched in all eight of its test usages and
never executed. The defence is the isolation, and the isolation is why the scope-relative
measurement is safe.

**Residual, stated:** for any FUTURE consumer that runs tests in the shared
worktree, `git_clean=true` in the observe packet now means "the named scope files
are clean". The only thing saying so is the `git_clean_semantics` string in the
packet — prose, not a machine guard. A consumer that reads the flag without the
prose will over-read it.

## Decision 2 — authoritative refs are MEASURED, never taken from the goal

`PreflightGate.REQUIRED_REFS` is `("git", "lease")`. `evidence_for` read `git` from
`goal.evidence["git_ref"]` — a field no producer ever wrote — so the ref was
permanently missing and step 4 blocked on it in **every packet the trail holds**
(495 of 495, measured 2026-08-11; see `BL-HERMES-CHAIN-DRIVE-001` for the caveat
about trail rotation). The inherited BL-4029 figure is `340 … samples` and it appears in FIVE files
(`task_classifier.py:78`, `faber_fitness.py:12`, `code_workflow.py:310`,
`tests/test_faber_fitness.py:30`, `tests/test_task_classifier.py:5`), not
four — and none of them says "observations". That wording was a quotation
this change invented and then attributed to prior code; it is corrected
here rather than propagated. Neither the number nor the phrasing is a
measurement this ADR made.

The producer now measures it (`git_head`), and falls back to the goal's own field
only when the measurement fails. The order is the point: a sha a goal reports about
itself is a quotation, not a measurement. This is `BL-4029 L6` one layer out — the
gate was fixed, the producer was not.

The same rule applies to `bl`/`cad`/`adr`: they are carried from the goal's own
`bl_ref`/`cad_ref`/`adr_ref` fields, because those ARE the goal's declaration of
which contract governs it. What must not be assumed is their *status*.

## Decision 3 — the driver may not manufacture a verdict, and may not skip a reason

- the review callable returns `ReviewVerdict.PENDING` with the measured `diff_id`;
- a goal is driven only when its remaining preflight reasons are exactly the ones
  step 6 removes (the lease pair). Any other reason means the goal is skipped WITH
  its reason recorded — a blocker is not removed by declining to look at it;
- `land` and `postcommit` are absent from the payload, so steps 11–13 are
  unreachable without a code change and an owner decision.

## Rejected alternatives

- **A `shadow=True` parameter.** A flag can be flipped by a caller, a config or a
  cron edit. Absence of a key cannot.
- **Building in the shared worktree and reverting after.** That is backup → mutate
  → restore on a tree eight streams write to, which this session measured producing
  false evidence twice.
- **Promoting `bl_status` from `reserved` to `open` so the chain proceeds.** That is
  the defect `BL-3673` was raised for, and reviewer blocked it there.
- **Letting the driver mark its own build reviewed** because tests passed. Tests are
  step 8 evidence; the reviewer verdict is step 10 and belongs to a role that can
  judge.
- **Widening `_drivable` to "any reason step 6 might plausibly fix".** The list is
  two exact strings; a wider rule silently drives goals blocked by something else.

## Consequences

- the chain is now called; before this it had zero callers;
- it stops at step 5 or step 7 on the live backlog, and that stop is TRUE about the
  world: no live goal carries a CAD or ADR reference, and all seven BLs are
  `reserved`;
- step 8 therefore does not execute in production today. It is exercised in tests
  and in an isolated copy, and that limitation is recorded rather than hidden;
- nothing is scheduled by this ADR. Putting the driver on a timer is a separate,
  named decision — see `BL-HERMES-CHAIN-DRIVE-001` G8.

## Open, and owned by the BL

`_drivable` RESTATES two reason strings that `PreflightGate` owns. The test no
longer hardcodes them — it derives the expected set by running the gate with
lease-only evidence, so a reword fails the test rather than silently turning the
driver into a no-op. What remains open under G7 is the restatement itself: the
driver still carries its own copy of a vocabulary another module defines.
