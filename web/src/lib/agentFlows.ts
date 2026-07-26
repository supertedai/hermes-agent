/**
 * agentFlows — pure state machine behind the chat sidebar's "agent-flow
 * chips" (BL-2555): one compact live card per delegate_task dispatch, built
 * from the relayed `subagent.*` frames on /api/events.
 *
 * Kept as a pure reducer (no React, no clock of its own) so the grouping
 * rules — which frame opens a chip, which updates a row, when a chip
 * freezes — are unit-testable without a WebSocket. Callers supply `now`
 * (ms epoch).
 *
 * Grouping model: `subagent.spawn_requested` at depth 0 opens a new flow;
 * later depth-0 frames attach to the LAST running flow (delegate_task runs
 * synchronously inside the parent's turn, so batches on one session never
 * interleave). Deeper frames (orchestrator grandchildren) are counted, not
 * given rows — the TUI spawn tree already renders that detail. A
 * `subagent.start` with no open flow (spawn frame missed after a reconnect)
 * opens one implicitly so the chip still appears mid-run.
 */

export type AgentRowState = "running" | "done" | "failed";

export interface AgentFlowRow {
  /** subagent_id when present, else a task_index-derived fallback key. */
  id: string;
  index: number;
  state: AgentRowState;
  /** Latest activity hint while running: tool name, progress text, "tenker". */
  activity?: string;
  /** Real per-child runtime, from the subagent.complete frame. */
  durationSeconds?: number;
  /** Child's closing summary (shown as tooltip, never as raw transcript). */
  summary?: string;
}

export interface AgentFlow {
  key: string;
  goal: string;
  taskCount: number;
  startedAt: number;
  endedAt?: number;
  state: "running" | "done" | "failed";
  rows: AgentFlowRow[];
  /** Spawns at depth > 0 (children of orchestrator children) — counted only. */
  nested: number;
}

const FAILED_STATUS = /fail|error|timeout|cancel|interrupt/i;
const ACTIVITY_MAX = 96;

function asStr(v: unknown): string | undefined {
  return typeof v === "string" && v.length > 0 ? v : undefined;
}

function asNum(v: unknown): number | undefined {
  return typeof v === "number" && Number.isFinite(v) ? v : undefined;
}

function trimActivity(v: string): string {
  return v.length > ACTIVITY_MAX ? `${v.slice(0, ACTIVITY_MAX - 1)}…` : v;
}

function rowKey(payload: Record<string, unknown>): string {
  return asStr(payload.subagent_id) ?? `idx-${asNum(payload.task_index) ?? 0}`;
}

/** Freeze a flow iff every known row is terminal — never guess an outcome. */
function maybeClose(flow: AgentFlow, now: number): AgentFlow {
  if (flow.state !== "running" || flow.rows.length === 0) return flow;
  if (flow.rows.length < flow.taskCount) return flow;
  if (flow.rows.some((r) => r.state === "running")) return flow;
  return {
    ...flow,
    state: flow.rows.some((r) => r.state === "failed") ? "failed" : "done",
    endedAt: now,
  };
}

function newFlow(payload: Record<string, unknown>, now: number): AgentFlow {
  return {
    key: `flow-${now}-${Math.floor(Math.random() * 1e6)}`,
    goal: asStr(payload.goal) ?? "delegert jobb",
    taskCount: Math.max(1, asNum(payload.task_count) ?? 1),
    startedAt: now,
    state: "running",
    rows: [],
    nested: 0,
  };
}

/**
 * Fold one `subagent.*` frame into the flow list. Returns a new array when
 * anything changed (safe for React setState), the same reference otherwise.
 */
export function applyAgentFlowEvent(
  flows: AgentFlow[],
  type: string,
  payload: Record<string, unknown> | null | undefined,
  now: number,
): AgentFlow[] {
  if (!type.startsWith("subagent.") || type === "subagent.text") return flows;
  const p = payload ?? {};
  const depth = asNum(p.depth) ?? 0;
  const openIdx = flows.reduce(
    (acc, f, i) => (f.state === "running" ? i : acc),
    -1,
  );

  if (type === "subagent.spawn_requested") {
    if (depth > 0 || asStr(p.parent_id)) {
      // A child of a child — count it on the open chip instead of opening one.
      if (openIdx < 0) return flows;
      const next = flows.slice();
      next[openIdx] = { ...next[openIdx], nested: next[openIdx].nested + 1 };
      return next;
    }
    // delegate_tool emits one spawn_requested PER CHILD (and today the
    // CLI→gateway relay drops them all — production chips open on the first
    // subagent.start instead). If a flow is already live, a spawn frame is
    // a row announcement for THAT dispatch, never a second chip — one card
    // per dispatch, even if these frames get plumbed through some day.
    if (openIdx >= 0) {
      const next = flows.slice();
      const flow = { ...next[openIdx], rows: next[openIdx].rows.slice() };
      next[openIdx] = flow;
      const key = rowKey(p);
      if (!flow.rows.some((r) => r.id === key)) {
        flow.rows.push({
          id: key,
          index: asNum(p.task_index) ?? flow.rows.length,
          state: "running",
          activity: "i kø",
        });
      }
      return next;
    }
    // Sequential dispatches: freeze a fully-terminal predecessor before the
    // new chip opens (its own close frame can be lost on reconnect).
    const next = flows.map((f) => maybeClose(f, now));
    next.push(newFlow(p, now));
    return next;
  }

  if (depth > 0 || asStr(p.parent_id)) return flows;

  let next: AgentFlow[];
  let idx = openIdx;
  if (idx < 0) {
    // Missed the spawn frame (reconnect mid-run): open implicitly.
    if (type === "subagent.complete" && flows.length > 0) {
      // A stray terminal frame with nothing open — attach to the last flow
      // if it knows the row, otherwise drop it (never fabricate a chip for
      // a run we cannot identify).
      const last = flows[flows.length - 1];
      if (!last.rows.some((r) => r.id === rowKey(p))) return flows;
      next = flows.slice();
      idx = flows.length - 1;
    } else if (type === "subagent.start") {
      next = flows.map((f) => maybeClose(f, now));
      next.push(newFlow(p, now));
      idx = next.length - 1;
    } else {
      return flows;
    }
  } else {
    next = flows.slice();
  }

  const flow = { ...next[idx], rows: next[idx].rows.slice() };
  next[idx] = flow;
  const key = rowKey(p);
  let rowIdx = flow.rows.findIndex((r) => r.id === key);
  if (rowIdx < 0) {
    flow.rows.push({
      id: key,
      index: asNum(p.task_index) ?? flow.rows.length,
      state: "running",
    });
    rowIdx = flow.rows.length - 1;
  }
  const row = { ...flow.rows[rowIdx] };
  flow.rows[rowIdx] = row;

  switch (type) {
    case "subagent.start":
      row.state = "running";
      // Clears a spawn-frame "i kø" placeholder — the child is now live.
      row.activity = undefined;
      break;
    case "subagent.thinking":
      if (row.state === "running") row.activity = "tenker";
      break;
    case "subagent.tool": {
      const tool = asStr(p.tool_name);
      if (row.state === "running" && tool) row.activity = tool;
      break;
    }
    case "subagent.progress": {
      const text = asStr(p.text) ?? asStr(p.summary);
      if (row.state === "running" && text) row.activity = trimActivity(text);
      break;
    }
    case "subagent.complete": {
      const status = asStr(p.status) ?? "";
      row.state = FAILED_STATUS.test(status) ? "failed" : "done";
      row.activity = undefined;
      row.durationSeconds = asNum(p.duration_seconds);
      const summary = asStr(p.summary);
      if (summary) row.summary = trimActivity(summary);
      break;
    }
    default:
      // Unknown subagent.* subtype: the row was ensured above so the chip
      // at least shows the agent as running; nothing else to record.
      break;
  }

  next[idx] = maybeClose(flow, now);
  return next;
}

/** "07s" under a minute, then "3m 12s", then "1t 04m" — mirrors the chip mock. */
export function formatClock(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const pad = (n: number) => String(n).padStart(2, "0");
  if (s < 60) return `${pad(s)}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${pad(s % 60)}s`;
  return `${Math.floor(s / 3600)}t ${pad(Math.floor((s % 3600) / 60))}m`;
}

/** Terminal rows so far — the header's "2/5" while a flow is live. */
export function doneCount(flow: AgentFlow): number {
  return flow.rows.filter((r) => r.state !== "running").length;
}
