# CAD-HERMES-CHAIN-DRIVE-001 — Three surfaces reach the code path; only one may drive it

**Status:** `ACCEPTED_ARCHITECTURE / IMPLEMENTATION_GATED`
**Parent:** `MWP-UOSH-001`
**Phase:** `P8 bounded autonomy` (entry work only; P8 itself stays `BLOCKED_BY_P1_P2_P4_P5`)
**Related:** `CAD-HERMES-LEARNING-LOOPS-001`, `CAD-MWP-ASI-CRITICAL-PATH-001`, `ADR-TRUTH-001`

## Problem

Three surfaces on `.15` can act on a coding request. Measured 2026-08-11:

```text
chat      tui_gateway/methods_prompt.py  ->  faber_live_adapter.run_live_faber_review
          fires on every coding-relevant turn.  ADVISES.  Writes nothing.
          NB: UNCOMMITTED. At HEAD that module calls record_coding_turn
          and contains no reference to run_live_faber_review at all; the
          wiring is a parallel stream's working-tree change (+40/-1 lines,
          importing the untracked agent/faber_chat_bridge.py). Cited by
          SYMBOL, and named as working-tree state, because a :NNN into
          an uncommitted file resolves to nothing in the record.

observe   */20 cron  ->  agent.faber_observe + agent.faber_goal_state
          reads the backlog, evaluates preflight.  MEASURES.  Builds nothing.

chain     agent.faber_runtime --tick-json  ->  GovernedCodeRunner
          the 13 governed steps.  ZERO CALLERS: not one cron line, systemd
          unit or script invoked it.
```

Seven parallel sessions built the seven chain components in one morning; `BL-4070`
wired them so `tests/test_chain_is_wired.py` reads `0 av 7 ukoblet`. The chain was
reachable and never reached.

**Precisely, because the loose version of this sentence was false.**
`GovernedCodeRunner` is instantiated in exactly one place in non-test code —
`FaberRuntime.__init__` (tests construct it 30+ times). And a `FaberRuntime` IS
constructed in production: `agent/agent_init.py:1811`, on every agent init,
fail-closed. What is zero is INVOCATION — `agent._faber_runtime` is written at
`agent_init.py:1806/1811` and read nowhere, and the only `.tick(` call sites
outside tests are `faber_runtime.py`'s own CLI.

The first draft of this CAD said "nothing constructed a `FaberRuntime`". That was
a false measurement in the load-bearing sentence of a register entry, caught in
review. It is recorded here rather than quietly corrected, because a register
entry that silently repairs its own claims teaches nobody.

A misleading string made this hard to see: the chat surface's failure path returns
`gate: "faber_runtime"`, but it never imports `faber_runtime`. A reader of that log
concludes the chain ran.

## Decision

**One driver, and it is the only surface permitted to enter the chain.**

```text
observe packet (measured)
        ↓
  drive_from_observe          <- the only caller of the 13 steps
        ↓
step 4  preflight, against MEASURED refs
step 6  lease TAKEN at the authority, released after
step 5  bl_gate      \
step 7  design_gate   >  block on the real state of the registers
step 8  build          /   — in an ISOLATED COPY of the verified sha
step 10 review        <- verdict PENDING; no verdict is manufactured
step 11 landing       <- unreachable by construction
```

The chat surface keeps advising and keeps writing nothing. The observe surface
keeps measuring and keeps claiming nothing. Neither gains capability here.

## Four structural properties

**1. Shadow is a shape, not a flag.** `payload_for` never emits a `land` or a
`postcommit` key. A flag can be set wrong; a key that is never written cannot be.
Landing capability is `ADR-062 V5` and hard-limit #3 — an owner decision, not a
parameter.

**2. The build never writes into the shared worktree.** Step 8 calls the model and
writes files. The worktree is shared by eight streams and carries ~120-130 dirty files (129 at the last reading — the number MOVES,
which is the point)
at any moment. The build root is `git archive <the sha the driver just
verified against the packet>` into a temporary directory, discarded after the
tick. This is also what makes scope-relative preflight safe —
see `ADR-HERMES-CHAIN-DRIVE-001`.

**3. No verdict is manufactured.** The driver supplies `ReviewVerdict.PENDING` with
the measured `diff_id`. A driver that sent `PASS` to proceed would be `BL-3673`
("writing a record so a gate lets you through") on a timer.

**4. Every gate must be REACHABLE.** A gate that no legitimate sequence of actions
can open is not a gate, it is a wall — `BL-4029 L4` established this and measured
the cost: `preflight_clear: 0 of 7` across every packet the trail holds (495 of
495, measured 2026-08-11; the inherited BL-4029 figure is `340 … samples` in
five files OF PRIOR CODE, not four, and none of them says "observations"). Any gate
this design touches must answer the falsifier: *is there a sequence of legitimate
actions that opens it?*

## Register dependency — the part that is NOT closed

Steps 5 and 7 read `source_refs["bl"]`, `["cad"]`, `["adr"]` and the matching
status fields. Measured on the live backlog: all seven goals carry `cad_ref=""`,
`adr_ref=""` and `bl_status="reserved"`. The chain therefore stops at step 5 or 7
for a reason that is **true about the world**, not about the code.

Closing that is the register bridge, and it is not this CAD's to close. The gap
named in `ADR-TRUTH-001` applies directly: a reference is checked for PRESENCE, not
for existence in any register. `BL-HERMES-CHAIN-DRIVE-001` carries the gates.

## Non-goals

- landing capability, and any automatic reviewer verdict;
- promoting a `reserved` BL to `open` to make the chain proceed;
- writing into the shared worktree from any scheduled path;
- treating a green test suite as evidence that the chain completes in production.
