# Continuous Hermes agent pipeline

This is the first implementation slice of the Opus/Hermes continuous-agent
contract.

## Contract

- Hermes owns the runtime loop, persistence, gates, and scheduling.
- Opus is the stable orchestration role, not a model identity.
- `ModelRouting` maps designer/reviewer and builder roles to configured
  substrates. The builder is replaceable (Luna, local 120B, or another
  configured substrate).
- The pipeline has exactly three outcomes: `OBSERVE`, `PROPOSE`, `ACT`.
- `ACT` is fail-closed: confidence must be at least `0.95`, the reasoner must
  not request more evidence, and the explicit approval callback must return
  true.
- The pipeline never treats missing memory layers as empty truth. They are
  returned in `MemorySnapshot.missing` with provenance for available layers.
- State is written atomically and bounded to the last 100 ticks.

## Code ownership and runtime wake

The pipeline is owned by the **Code** domain and stewarded by **faber**. Every
optimization loop in this Code projection carries `owner="faber"`, and the
runtime wake records `projection="code"`. This does **not** make faber the
global owner of Mortens user memory, Cortex memory, or every Symbiose layer.
The `runtime_open()` bootstrap is now called from Hermes' primary agent
initialization as a read-only event. It does not start a second scheduler,
create a store, or authorize an action; the existing MemoryManager/MemoryProvider
lifecycle remains authoritative.

The baseline registry contains explicit loops for:

- runtime wake
- context freshness
- memory integrity
- epistemic gating
- goal review
- skill candidates
- workflow candidates
- execution verification
- learning measurement
- rollback observability

Each loop has a phase, cadence, mode, and approval requirement. This is a
measurable registry, not an assertion that every possible future optimization
has already been implemented.

## Memory Scheduler and cost control

The `MemoryScheduler` is a selector over existing canonical memory readers; it
is **not** a new memory store. This follows ADR-038 D3/D4: each layer keeps its
existing storage, writer, reader, instance, scope, provenance, freshness,
correction, runtime-test, failure mode, and rollback contract. Existing
memory work such as BL-1378, BL-2651, BL-2862, BL-3253 and BL-3254 remains the
source of truth and is not reimplemented here.

The scheduler:

- reserves phase-required governance layers first;
- ranks optional layers by priority, relevance, freshness and retrieval cost;
- enforces a per-tick token budget;
- reports excluded layers and budget overflow instead of silently dropping
  required context;
- records the selection in `TickResult` for later learning and audit.

`MemoryManagerBridge` is the integration seam around the existing Hermes
provider hooks: `prefetch_all`, `sync_all`, `queue_prefetch_all`,
`on_pre_compress`, and `on_session_end`. It adds selection/budget telemetry but
leaves provider retrieval, scope, async ordering and persistence authoritative.

The `CostAwareModelRouter` keeps retrieval, freshness and verification
deterministic (no LLM call), uses a cheap configured local route for low-risk
classification/summarization, and reserves the configured designer/reviewer
route for quality-critical design, epistemic reasoning and review. Model
references are configuration keys; no model identity is hardcoded into the
Opus role.

## Integration boundary

`agent/continuous_pipeline.py` is a pure orchestration kernel. Hermes-specific
model/tool adapters must implement `PipelineAdapter` and connect it to the
existing cron/runtime lifecycle. This prevents model/provider details from
becoming the agent's identity and makes the kernel deterministic to test.

The kernel is intentionally not scheduled by this change. The 20-minute
scheduler location (.12 versus the Hermes runtime on .15) is an architectural
choice that must be recorded and gated under BL-2627 before activation. Until
then, the module can be embedded in a cron job or gateway adapter in
`OBSERVE`/`PROPOSE` mode.

## Governed Code workflow

`agent/code_workflow.py` turns the operational rails into a fail-closed state
machine owned by Faber's Code projection:

```text
candidate → proposed → approved → planned → building → verified
          → landed → measured → learned → proposed
```

`PreflightGate` blocks build planning when Git/lease, CAD, ADR, BL or Brain /
Obsidian evidence is dirty, stale, reconstructed or unknown. `GoalLedger`
requires preflight evidence before build states, test evidence before
`verified`, reviewer PASS before `landed`, and runtime/effect evidence before
`measured`/`learned`. `DefinitionOfDone` requires commit, reviewer PASS, tests,
readback, runtime smoke, rollback, Change Log and SelfState evidence.

If a gate blocks progress, the goal enters `blocked` and emits a durable
`FaberHandoff` containing the checkpoint state, blocker, required gate and
next step. The next Code/Faber job resumes only at that checkpoint. This keeps
work continuous without bypassing reviewer or Morten hard-limit gates. A
blocked job may checkpoint and hand off; it may not commit past a required
reviewer gate.

The gate consumes evidence from the existing CAD/ADR/BL/Brain systems; it does
not mint or mutate those systems by itself.

`GovernedCodeRunner` is the single ordering point for the local workflow:
preflight → goal approval → plan → build → tests → reviewer → landing evidence.
On any gate failure it returns `BLOCKED` plus a Faber handoff instead of
pretending that the job is done. It does not itself commit or start live
infrastructure; those actions remain explicit adapters behind their gates.

The canonical Code memory registry is the exact 20-layer `_MEM_LAYERS` set from
the CAD/ADR source (`episodisk`, `semantisk`, `erfaring`, `kausalt`,
`epistemisk`, `temporalt`, `proseduralt`, `prospektivt`, `autobiografisk`,
`sosialt`, `assosiativt`, `salient`, `governance`, `kontrafaktisk`,
`konsolidering`, `metaminne`, `reflektivt`, `utility`, `prediksjon`,
`affordance`). The older 9-layer CMC/SMM taxonomy is legacy and cannot be
silently mixed into the canonical scheduler.

## Verification

Run the targeted test when the checkout's development dependencies are
available:

```bash
uv run pytest -q tests/test_continuous_pipeline.py
```

The stdlib smoke test and `compileall` must pass even in a lean installation.
