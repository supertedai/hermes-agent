/**
 * agentFlows reducer tests (BL-2555) — the grouping rules the sidebar chips
 * depend on, exercised frame-by-frame without a WebSocket. Payload shapes
 * mirror tui_gateway/server.py's subagent relay (`server.py:4170-4232`).
 */
import { describe, expect, it } from "vitest";

import {
  applyAgentFlowEvent,
  doneCount,
  formatClock,
  type AgentFlow,
} from "./agentFlows";

const T0 = 1_000_000;

function run(
  frames: Array<[string, Record<string, unknown>]>,
  start: AgentFlow[] = [],
): AgentFlow[] {
  let flows = start;
  let now = T0;
  for (const [type, payload] of frames) {
    now += 1_000;
    flows = applyAgentFlowEvent(flows, type, payload, now);
  }
  return flows;
}

describe("applyAgentFlowEvent", () => {
  it("opens a chip on spawn_requested and tracks rows to completion", () => {
    const flows = run([
      ["subagent.spawn_requested", { goal: "inventer hostene", task_count: 2 }],
      ["subagent.start", { task_index: 0, subagent_id: "a" }],
      ["subagent.start", { task_index: 1, subagent_id: "b" }],
      ["subagent.tool", { subagent_id: "a", tool_name: "graph_query" }],
      ["subagent.complete", { subagent_id: "a", status: "completed", duration_seconds: 41 }],
      ["subagent.complete", { subagent_id: "b", status: "completed", duration_seconds: 65 }],
    ]);
    expect(flows).toHaveLength(1);
    const f = flows[0];
    expect(f.goal).toBe("inventer hostene");
    expect(f.state).toBe("done");
    expect(f.endedAt).toBeDefined();
    expect(f.rows.map((r) => r.state)).toEqual(["done", "done"]);
    expect(f.rows[0].durationSeconds).toBe(41);
  });

  it("stays running until every row is terminal", () => {
    const flows = run([
      ["subagent.spawn_requested", { goal: "g", task_count: 2 }],
      ["subagent.start", { task_index: 0, subagent_id: "a" }],
      ["subagent.start", { task_index: 1, subagent_id: "b" }],
      ["subagent.complete", { subagent_id: "a", status: "completed" }],
    ]);
    expect(flows[0].state).toBe("running");
    expect(doneCount(flows[0])).toBe(1);
  });

  it("marks the flow failed when any child fails", () => {
    const flows = run([
      ["subagent.spawn_requested", { goal: "g", task_count: 1 }],
      ["subagent.start", { task_index: 0, subagent_id: "a" }],
      ["subagent.complete", { subagent_id: "a", status: "error: timeout" }],
    ]);
    expect(flows[0].rows[0].state).toBe("failed");
    expect(flows[0].state).toBe("failed");
  });

  it("keeps sequential dispatches as separate receipt chips (M2)", () => {
    const flows = run([
      ["subagent.spawn_requested", { goal: "steg 1", task_count: 1 }],
      ["subagent.start", { task_index: 0, subagent_id: "a" }],
      ["subagent.complete", { subagent_id: "a", status: "completed" }],
      ["subagent.spawn_requested", { goal: "steg 2", task_count: 1 }],
      ["subagent.start", { task_index: 0, subagent_id: "b" }],
    ]);
    expect(flows).toHaveLength(2);
    expect(flows[0].state).toBe("done");
    expect(flows[1].state).toBe("running");
    expect(flows[1].goal).toBe("steg 2");
  });

  it("opens an implicit chip when the spawn frame was missed", () => {
    const flows = run([
      ["subagent.start", { task_index: 0, subagent_id: "a", goal: "sen start" }],
    ]);
    expect(flows).toHaveLength(1);
    expect(flows[0].rows).toHaveLength(1);
    expect(flows[0].state).toBe("running");
  });

  it("follows the production start-first path for a multi-task dispatch", () => {
    // The CLI→gateway relay drops spawn_requested frames entirely — a real
    // dispatch arrives as start/tool/complete only (reviewer BL-2555).
    const flows = run([
      ["subagent.start", { goal: "inventar", task_count: 3, task_index: 0, subagent_id: "a" }],
      ["subagent.start", { goal: "inventar", task_count: 3, task_index: 1, subagent_id: "b" }],
      ["subagent.tool", { subagent_id: "b", tool_name: "read_file", task_count: 3 }],
      ["subagent.start", { goal: "inventar", task_count: 3, task_index: 2, subagent_id: "c" }],
      ["subagent.complete", { subagent_id: "a", status: "completed", duration_seconds: 12, task_count: 3 }],
      ["subagent.complete", { subagent_id: "b", status: "ok", duration_seconds: 18, task_count: 3 }],
      ["subagent.complete", { subagent_id: "c", status: "completed", duration_seconds: 25, task_count: 3 }],
    ]);
    expect(flows).toHaveLength(1);
    expect(flows[0].taskCount).toBe(3);
    expect(flows[0].goal).toBe("inventar");
    expect(flows[0].rows).toHaveLength(3);
    expect(flows[0].state).toBe("done");
  });

  it("never fragments one dispatch into several chips on per-child spawn frames", () => {
    const flows = run([
      ["subagent.spawn_requested", { goal: "g", task_count: 3, task_index: 0 }],
      ["subagent.spawn_requested", { goal: "g", task_count: 3, task_index: 1 }],
      ["subagent.spawn_requested", { goal: "g", task_count: 3, task_index: 2 }],
    ]);
    expect(flows).toHaveLength(1);
    expect(flows[0].rows).toHaveLength(2); // frame 1 opens the chip; 2+3 become queued rows
    expect(flows[0].rows.every((r) => r.activity === "i kø")).toBe(true);
  });

  it("counts nested spawns instead of adding rows", () => {
    const flows = run([
      ["subagent.spawn_requested", { goal: "g", task_count: 1 }],
      ["subagent.start", { task_index: 0, subagent_id: "a" }],
      ["subagent.spawn_requested", { goal: "barnebarn", task_count: 2, depth: 1, parent_id: "a" }],
      ["subagent.tool", { subagent_id: "x", tool_name: "read_file", depth: 1, parent_id: "a" }],
    ]);
    expect(flows).toHaveLength(1);
    expect(flows[0].nested).toBe(1);
    expect(flows[0].rows).toHaveLength(1);
  });

  it("records activity hints and clears them on completion", () => {
    const flows = run([
      ["subagent.spawn_requested", { goal: "g", task_count: 1 }],
      ["subagent.start", { task_index: 0, subagent_id: "a" }],
      ["subagent.thinking", { subagent_id: "a" }],
      ["subagent.progress", { subagent_id: "a", text: "leser census" }],
      ["subagent.complete", { subagent_id: "a", status: "completed", summary: "23 funnet" }],
    ]);
    const row = flows[0].rows[0];
    expect(row.activity).toBeUndefined();
    expect(row.summary).toBe("23 funnet");
  });

  it("ignores subagent.text and non-subagent frames", () => {
    const base = run([["subagent.spawn_requested", { goal: "g", task_count: 1 }]]);
    expect(applyAgentFlowEvent(base, "subagent.text", { text: "x" }, T0)).toBe(base);
    expect(applyAgentFlowEvent(base, "tool.start", {}, T0)).toBe(base);
  });

  it("drops stray terminal frames it cannot attribute", () => {
    const flows = applyAgentFlowEvent(
      [],
      "subagent.complete",
      { subagent_id: "ghost", status: "completed" },
      T0,
    );
    expect(flows).toEqual([]);
  });

  it("tolerates missing/odd payload fields", () => {
    const flows = run([
      ["subagent.spawn_requested", {}],
      ["subagent.start", { task_index: "not-a-number" as unknown as number }],
    ]);
    expect(flows).toHaveLength(1);
    expect(flows[0].taskCount).toBe(1);
    expect(flows[0].rows).toHaveLength(1);
  });
});

describe("formatClock", () => {
  it("formats like the approved chip mock", () => {
    expect(formatClock(7)).toBe("07s");
    expect(formatClock(192)).toBe("3m 12s");
    expect(formatClock(3840)).toBe("1t 04m");
  });
});
