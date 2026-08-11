# BL-HERMES-CHAIN-DRIVE-001 — The chain is called; the registers it reads are not verified

**Status:** `PARTIAL / GATES_OPEN`
**Parent:** `MWP-UOSH-001 → CAD-HERMES-CHAIN-DRIVE-001 → ADR-HERMES-CHAIN-DRIVE-001`
**Phase:** `P8` entry work. P8 itself remains `BLOCKED_BY_P1_P2_P4_P5`.
**Symbiose BL:** `BL-4087` (allocated via `tools/allocate_bl.py` on `.13`, never hand-picked)

| Gate | Requirement | Status |
|---|---|---|
| G1 | A caller for the 13 steps exists in the codebase (INVOCATION is G8) | `CLOSED` |
| G2 | Step 4 opens on a real goal, with measured refs | `PARTIAL` |
| G3 | Step 6 claims at the authority and releases after | `PARTIAL` |
| G4 | Skill selection reaches the driven chain | `PARTIAL` |
| G5 | Build never writes into the shared worktree | `CLOSED` |
| G6 | A contract ref is VERIFIED against a register | `OPEN` |
| G7 | `_drivable` cannot go silently empty on a reword | `OPEN` |
| G8 | The driver runs on a schedule | `OWNER_GATED` |
| G9 | A reviewer judges the build (step 10) | `OWNER_GATED` |
| G10 | Landing capability (step 11–13) | `OWNER_GATED` |
| G11 | Step 8 executes in production, not only in tests | `BLOCKED_BY_G6` |
| G12 | Missing CAD/ADR is judged by `DesignGate`, not raised as a ledger exception | `OPEN` |

## What is measured — and the exact provenance of it

Before this work: `preflight_clear: 0 of 7`. The inherited BL-4029 figure is `340 … samples`,
in FIVE files OF PRIOR CODE, not four — and none of them says "observations". Both the
count and the quoted wording were wrong in my first three attempts at this
sentence; the quotation was invented here and attributed to prior code.

Measured live: **495 of 495 packets** in the trail carry the reason, and **0** have
`preflight_clear > 0`. My first attempt at replacing the inherited number said
"492" — wrong, in the very paragraph whose purpose was to replace an inherited
number with a measured one. The correct figure is every packet the trail holds.

**The date range is a FLOOR, not a start.** `TRAIL_LIMIT = 500` in
`agent/faber_observe.py` (cited by SYMBOL: the fix that corrected the number
above grew a docstring and moved the constant, so the line number it had
been cited by was already wrong — which is exactly how a `:NNN` citation
rots, by being edited near) rotates the file, and it stands at 495. So
`2026-08-04T19:57Z → 2026-08-11T12:20Z` is what survived rotation, not when the
condition began — and within roughly a hundred minutes it will be purely an
artifact of the window. Read it as "at least this long".

Blocked on
`missing authoritative source refs: git, lease` · `git target is dirty` ·
`target lease is not clear`. The trail
(`~/.hermes-gui/faber/observe-last.trail.jsonl`, 495 entries) contains **zero**
entries with `preflight_clear > 0` and **zero** observations whose reason set was
drivable-shaped.

One driven run reached step 5 on 2026-08-11 ~11:25 UTC:

```text
preflight   PASS        reasons: []
lease       4 paths claimed at the authority, released after
skills      3 selected, coverage=complete
state       blocked     gate=bl_gate
blocker     BL status is not actionable: reserved
```

**Its provenance, stated because the label "live backlog" was wrong and review
caught it.** The registry and the goal were live. The packet was NOT: it came from
a manual run of the producer, written to `/tmp`, at a moment when
`agent/faber_runtime.py` — which is in that goal's `repo_scope` — happened to be
clean.

**And my first correction of this paragraph was itself false.** It said "the `*/20`
cron still runs the OLD producer". It does not. The cron line is
`cd …/hermes-agent && .venv/bin/python -m agent.faber_observe`, and `-m` with that
cwd loads the **working-tree** module. The producer change went live on the timer
the moment the file was saved. The trail shows it: the `11:20:02Z` packet has the
old shape; the file's mtime is `11:25:46Z`; the `11:40:17Z` and `12:00:02Z`
packets — both scheduled runs — carry `git_ref`, `repo_dirty_files`, `scope_dirty`
and `git_clean_semantics`.

**So the producer half is DE-FACTO DEPLOYED, uncommitted, on a `*/20` timer**,
and it was deployed before this review returned. That is precisely the "live code
that is not in git" hazard CLAUDE.md names, created here while writing about it.
The driver half is not scheduled — G8 holds — because nothing invokes
`--drive-observe`. Recorded here rather than left to be discovered.

Driving against the live SCHEDULED `12:00:02Z` packet gives **0 of 7**, for the
reason the next paragraph gives — not for a deploy that is pending.

**And it is not reproducible today, for a reason that is the gate working.** This
change edits `agent/faber_runtime.py`, so that goal's scope is now dirty and the
scope-relative check blocks it. A live driven run right now drives **0 of 7**, all
seven skipped with named reasons.

G2/G3/G4 are therefore `PARTIAL`, not `CLOSED`: the mechanism is demonstrated, the
production path is not. The closing condition is simply a POST-COMMIT run — the
scheduled producer is already the fixed one.

**And a post-commit run drives at most 2 of 7, not 7 of 7.** Measured on the live
`12:20:01Z` packet: goals 4–7 carry `git_ref: ""` and `repo_dirty: -1` because the
cron line passes `--repo` for only three goal ids, and goal 3 is blocked on
`codebase absent on this host: agi` (ADR-062 V2 forbids checking AGI out here).
Five of seven are blocked by things a commit cannot fix. Until this change is committed, the
goals' scopes contain the very files being edited, so the scope-relative gate
blocks them, correctly.

## G6 is the load-bearing gate, and it is the register bridge

No gate anywhere in the chain verifies a contract reference against a register.
`DesignGate.evaluate` checks that `source_refs["cad"]` and `["adr"]` are non-empty
strings, plus a `cad_status`/`adr_status` that the PRODUCER asserts. `BlGate`
checks presence plus a producer-asserted `bl_status`. `parse_contract_ref` in the
classifier checks FORM only, and says so.

So today a goal can name `ADR-HERMES-CHAIN-DRIVE-001` or `ADR-DOES-NOT-EXIST-999`
and both clear step 7 identically, provided someone wrote `accepted` into the
status field. That is the control-that-cannot-fail this repository condemns
elsewhere, sitting in the gate that decides whether design review happened.

Closing G6 means the producer RESOLVES each ref against this register directory and
derives the status from the document's own `**Status:**` line — an absent document
must yield a BLOCK naming the missing register entry, not a silent pass.

Until G6 closes, G11 cannot close: driving a goal to step 8 in production would mean
a build authorised by a design reference nobody verified.

## G12 — the step-7 gate is unreachable for the case it exists for

Measured 2026-08-11, driving a goal with an actionable BL and no CAD/ADR:

```text
preflight PASS   gate=runner   next_step="inspect and retry"
blocker: runner exception: ValueError: goal references required before build: cad_ref, adr_ref
```

The absence IS caught — but by `FaberGoalLedger.transition`, as an exception, and
the runner's outer handler turns it into `gate="runner"` with
`next_step="inspect and retry"`. `DesignGate`, which exists precisely to judge CAD
and ADR at step 7 and to name the next action, never runs: the transition guard
fires first.

So the objection is right and the diagnosis is useless. A next_step that names no
action is the one thing `BL-4029` established a handoff must never produce.

Reordering the runner's guards is a separate decision with its own review, and is
not folded into the commit that found it. The regression test pins the CURRENT
behaviour and states in place that closing G12 must update this row.

## G8–G10 are owner-gated, and the reason is recorded

Scheduling the driver, wiring a reviewer verdict, and granting landing capability
are `ADR-062 V5` and hard-limit #3. They are not withheld because they are hard;
they are withheld because they are Morten's to grant. The code is shaped so each
requires a deliberate, visible change:

- scheduling → a cron line that does not exist;
- reviewer → replacing a `PENDING` literal;
- landing → adding a `land` key `payload_for` never writes.

## Closeout requires

Producer-side register resolution with a named BLOCK on an absent document (G6); a
`_drivable` rule derived from `PreflightGate` rather than restated (G7); and, for
G11, one driven run in which step 8 executes against a goal whose CAD, ADR and BL
all resolve to real, accepted documents. Test-suite green and a driven run that
stops early cannot close G11 — the chain stopping honestly is evidence that the
gates work, not that the work happened.

## 2026-08-11 — what this entry does NOT claim

The chain has a caller IN THE CODEBASE. Nothing invokes it on a schedule: cron
lines calling `--drive-observe` = 0, systemd units = 0, scripts = 0. By the same
standard this CAD used to open the problem ("zero callers"), G1 measures code
reachability and G8 measures invocation — they are different claims and are kept
apart. The chain has not completed. No goal has been built, reviewed,
landed or measured by it, and none can be until G6 and the owner gates move. The
seven live goals stop at step 5 because all seven BLs are `reserved` and all seven
carry `cad_ref=""`, `adr_ref=""` — a true statement about the backlog, produced by
gates doing their job.
